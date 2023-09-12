#!/usr/bin/env python

import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple, Union, Optional

from lxml import etree

from maven import Artifact, Component, Environment, Model


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
    """
    TODO
    """

    def __init__(self):
        # Set of artifacts (both current and previous) included in the db.xml.
        self.artifacts: Set[Artifact] = set()
        # Set of *current* artifacts included in the db.xml.
        self.current: Set[Artifact] = set()
        # Components whose dependencies have already been processed.
        self.components: Set[Component] = set()

    def add_artifact(self, artifact: Artifact, current_version: bool = True):
        # Register artifact.
        if not self._register_artifact(artifact, current_version):
            # Artifact already processed.
            return

        # Register dependencies.
        self._register_dependencies(artifact, current_version)

        # Register other/"previous" versions of the artifact.
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
        model = Model(artifact.component.pom())
        for dep in model.dependencies():
            if dep.scope not in ("compile", "runtime"): continue
            self._register_artifact(dep.artifact, current_version)

    def generate_xml(self, template_path: Union[Path, str]) -> str:
        # NB: The remove_blank_text=True option is needed to pretty-print the XML output later:
        # https://lxml.de/FAQ.html#why-doesn-t-the-pretty-print-option-reformat-my-xml-output
        with open(template_path) as f:
            tree = etree.parse(f, parser=etree.XMLParser(remove_blank_text=True))

        # In Updater terms, a <plugin> entry is a (G, A, C, P) tuple at all versions.
        # Therefore, we make a list of artifacts (i.e. versions) for each GACP.
        plugins: Dict[Plugin, List[Artifact]] = {}
        for artifact in self.artifacts:
            plugin: Plugin = (artifact.groupId, artifact.artifactId, artifact.classifier, artifact.packaging)
            if plugin not in plugins:
                plugins[plugin] = []
            plugins[plugin].append(artifact)

        # Now that we have our list of plugins, we can generate the corresponding XML elements.
        # CTR TODO: sort by artifactId? Or by groupId/artifactId? Or by something else?
        for _, artifacts in plugins.items():
            self._populate_plugin(tree, artifacts)

        return etree.tostring(tree, xml_declaration=True, pretty_print=True, encoding="utf-8").decode()

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
            for dep in model.dependencies():
                if dep.scope not in ("compile", "runtime"): continue
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


# -- Main --

def main(args):
    debug = bool(os.environ.get("DEBUG", None))
    log_format = "[%(levelname)s] %(message)s"
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(format=log_format, level=log_level)

    # Create appropriate Maven environment.
    storage = Path("/opt/sonatype-work/nexus/storage")
    release_repos = ["releases", "thirdparty", "sonatype", "sonatype-s01", "central", "ome-releases"]
    snapshot_repos = ["snapshots", "sonatype-snapshots", "sonatype-snapshots-s01", "ome-snapshots"]
    local_repos = [repo for r in release_repos + snapshot_repos if (repo := storage / r).exists()]
    remote_repos = {
        "scijava.public": "https://maven.scijava.org/content/groups/public"
    }
    print("Creating Maven environment...")
    env = Environment(local_repos=local_repos, remote_repos=remote_repos)
    #def fail_download(*args):
    #    raise RuntimeError(f"Should not be downloading: {args[0]}")
    #env.resolver.download = fail_download

    print("Initializing FilesCollection...")
    fc = FilesCollection()

    # Process arguments.
    coords = [arg for arg in args if ":" in arg]
    for coord in coords:
        print(f"Processing {coord}...")
        tokens = coord.split(":")
        g = tokens[0]
        a = tokens[1]
        project = env.project(g, a)
        v = tokens[2] if len(tokens) > 2 else project.release
        component = project.at_version(v)
        artifact = component.artifact()
        print(f"Adding artifact {artifact}...")
        fc.add_artifact(artifact)

    print("Generating resultant XML...")
    xml = fc.generate_xml("template.xml")
    with open(f"db-{g}-{a}-{v}.xml", "w") as f:
        f.write(xml)


if __name__ == "__main__":
    main(sys.argv[1:])
