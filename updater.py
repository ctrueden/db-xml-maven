#!/usr/bin/env python

from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple, Union, Optional

from lxml import etree

from maven import Artifact, Component, Model


# -- Type aliases --


# In Maven terms, a <plugin> entry is a (G, A, C, P) tuple at all versions.
Plugin = Tuple[str, str, str, str]


# -- Functions --

def checksum(path: Path):
    # CTR FIXME: Calculate the Updater's crazy checksum!
    return "8dee3846e4ca1a0ad4169cf5e4859bcf52b878af"


def timestamp(path: Path) -> str:
    """Get a timestamp string of the form YYYYMMDDhhmmss."""
    mtime = path.stat().st_mtime
    dt = datetime.fromtimestamp(mtime)
    return dt.strftime("%Y%m%d%H%M%S")


def deduce_platform(classifier: str) -> Optional[str]:
    if "mac" in classifier:
        return "macosx"

    if "win" in classifier:
        platform = "win"
    elif "linux" in classifier:
        platform = "linux"
    else:
        # Unknown operating system family.
        return None

    if any(arch in classifier for arch in ("amd64", "x86_64")):
        platform += "64"
    elif any(arch in classifier for arch in ("x86", "i586")):
        platform += "32"
    else:
        # Unknown architecture.
        return None

    return platform


# -- Classes --

class FilesCollection:
    # GACP = <plugin>
    # GAVCP = <version> or <previous-version>
    # - <version> only when we are in the primary populate phase, rather than the "scan back through maven-metadata.xml" phase
    # - dependency list only when <version> and C=""

    # huge bag of GAVCP's i.e. Artifacts
    # sort it into GACP -> List[V]
    #
    # for each (G, A, C, P):
    #   make a list of Vs.
    #   If that GACVP appears on the *current GACVP list* then it's current, otherwise it's previous-version.
    #

    def __init__(self):
        self.components: Set[Component] = set()
        self.artifacts: Set[Artifact] = set()
        self.current: Set[Artifact] = set()

    def add_artifact(self, artifact: Artifact, current_version: bool = True):
        # Register artifact.
        if not self._register_artifact(artifact, current_version):
            # Artifact already processed.
            return

        # Register dependencies.
        self._register_dependencies(artifact, current_version)

        # Register previous versions of the artifact.
        # CTR FIXME: two things:
        # 1. This enumerates *all* versions of the artifact, not only *previous* ones. Might want a version comparator here.
        # 2. There is no guarantee that this particular GACP exists at every previous version. Use a try/except when resolving the path, either here or during XML generation.
        for component in artifact.component.project.versions():
            previous_artifact = component.artifact(classifier=artifact.classifier, packaging=artifact.packaging)
            self.add_artifact(previous_artifact, False)

    def _register_artifact(self, artifact: Artifact, current_version: bool) -> bool:
        if artifact in self.artifacts:
            # Artifact already processed.
            return False
        self.artifacts.add(artifact)
        print(f"Registered {artifact}{' <-- CURRENT' if current_version else ''}")
        if current_version:
            self.current.add(artifact)
        return True

    def _register_dependencies(self, artifact: Artifact, current_version: bool) -> None:
        if artifact.component in self.components:
            # This component's dependencies have already been processed.
            return
        self.components.add(artifact.component)
        effective_pom = artifact.component.pom(interpolated=True)
        for dep in effective_pom.dependencies():
            if dep.scope in ("compile", "runtime"):
                self._register_artifact(dep.artifact, current_version)

    def generate_xml(self, template_path: Union[Path, str]) -> str:
        with open(template_path) as f:
            tree = etree.parse(f)

        # In Updater terms, a <plugin> entry is a (G, A, C, P) tuple at all versions.
        # Therefore, we make a list of artifacts (i.e. versions) for each GACP.
        plugins: Dict[Plugin, List[Artifact]] = {}
        for artifact in self.artifacts:
            plugin: Plugin = (artifact.groupId, artifact.artifactId, artifact.classifier, artifact.packaging)
            if plugin not in plugins:
                plugins[plugin] = []
            plugins[plugin].append(artifact)

        # Now that we have our list of plugins, we can generate the corresponding XML elements.
        # CTR FIXME: sort by artifactId? Or by groupId/artifactId? Or by something else?
        for _, artifacts in plugins.items():
            self._populate_plugin(tree, artifacts)

        return etree.tostring(tree, xml_declaration=True, encoding="utf-8").decode()

    def _populate_plugin(self, tree, artifacts: List[Artifact]) -> None:
        # Discern which version is the current one.
        current_artifacts = [a for a in artifacts if a in self.current]
        assert len(current_artifacts) <= 1
        current_artifact = current_artifacts[0] if current_artifacts else None
        default_artifact = current_artifact or artifacts[0]

        # <plugin> tag
        plugin = etree.SubElement(tree.getroot(), "plugin")
        plugin.set("filename", default_artifact.filename)

        # <platform> tag
        platform_string = deduce_platform(default_artifact.classifier)
        if platform_string:
            platform = etree.SubElement(plugin, "platform")
            platform.text = platform_string

        if current_artifact:
            # <version> tag
            version = etree.SubElement(plugin, "version")
            artifact_path = current_artifact.resolve()
            version.set("checksum", checksum(artifact_path))
            version.set("timestamp", timestamp(artifact_path))
            version.set("filesize", str(artifact_path.stat().st_size))

            # <description> tag
            pom = current_artifact.component.pom()
            desc = pom.description
            if desc:
                description = etree.SubElement(version, "description")
                description.text = desc

            # <dependency> tags
            model = Model(pom)
            for dep in model.dependencies(transitive=True):
                dependency = etree.SubElement(version, "dependency")
                dependency.set("filename", f"jars/{dep.artifact.filename}")
                dependency.set("timestamp", timestamp(dep.artifact.resolve()))

            # <author> tags
            # Use developers and contributors from the POM, founders first, then others.
            people = pom.developers + pom.contributors
            founders = [p for p in people if "founder" in p.get("roles", [])]
            others = [p for p in people if p not in founders]
            for person in founders + others:
                name = person.get("name", person.get("id", None))
                author = etree.SubElement(version, "author")
                author.text = name

        # <previous-version> tags
        # CTR FIXME: need maven-metadata.xml I guess
        # Need to build up a complete set of dependencies across all previous versions, in addition to only those for the current version.
        # every <plugin> is an artifact, which is reflected in the method sig.
        # every dependency is also translated into an artifact.
        # build up details in data structures (queue, set, and/or dict)
        # then call add_plugin recursively on the data structure.
        for artifact in artifacts:
            if artifact == current_artifact:
                # Not a "previous" version!
                continue
            previous_version = etree.SubElement(plugin, "previous-version")
            artifact_path = artifact.resolve()
            previous_version.set("timestamp", timestamp(artifact_path))
            # previous_version.set("timestamp-obsolete", "0")
            previous_version.set("checksum", checksum(artifact_path))
            previous_version.set("filename", f"jars/{artifact.filename}")
