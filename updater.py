#!/usr/bin/env python

from pathlib import Path
from datetime import datetime
from typing import Dict, Set, List

from lxml import etree

from maven import Artifact, Component, Dependency, Project


# -- Functions --

def timestamp(path: Path) -> str:
    """Get a timestamp string of the form YYYYMMDDhhmmss."""
    mtime = path.stat().st_mtime
    dt = datetime.fromtimestamp(mtime)
    return dt.strftime("%Y%m%d%H%M%S")


def deduce_platform(classifier: str) -> str:
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


def dependencies(artifact: Artifact) -> List[Dependency]:
    pom = artifact.component.pom()
    for dependency in pom.dependencies(artifact.env):
        pass


# -- Classes --

class FilesCollection:
    # GACP = <plugin>
    # GAVCP = <version> or <previous-version>
    # - <version> only when we are in the primary populate phase, rather than the "scan back through maven-metadata.xml" phase
    # - dependency list only when <version> and C=""

    def __init__(self):
        self.projects: Set[Project] = set()
        self.components: Set[Component] = set()
        self.files: Dict[Project, Set[Artifact]] = {}
        self.current: Set[Artifact] = set()

            project = artifact.component.project
            projects.add(project)

            versions.k$

    def _process_artifact(artifact: Artifact, previous: bool = False):
        # Track artifact and its project within the data structures.
        project = artifact.component.project
        projects.add(project)
        if project not in versions:
            versions[project] = set()
        versions[project].add(artifact)

        if not previous:
            current.add(artifact)

        _process_component(artifact.component, previous)

    def _process_component(component: Component, previous: bool = False):
        if component in self.components:
            # Component already processed.
            return

        # Process previous versions.
        pass

    def load(self, path):
        # CTR FIXME: disable general purpose loading, because we don't want to support parsing existing XML into the supporting data structures.
        # we just want to build up the XML based on those data structures which are computed from maven objects.
        with open(path) as f:
            self.tree = etree.parse(f)

    def save(self, path):
        xml = etree.tostring(self.tree, xml_declaration=True, encoding="utf-8").decode()
        with open(path, "w") as f:
            f.write(xml)

    def add_plugin(self, artifact: Artifact, current: Dict[Project, Artifact] = None):
        # Toplevel artifact added:
        # we have the entire list of deps including transitives.
        # put every item on this list into the current artifact dictionary.
        #
        if current is None:
            current = {}
            current[artifact.component.project] = artifact
        for dep in deps(artifact):

        # for each dependency, there is an artifact.
        # each artifact has a list of dependencies.
        # each artifact is either *current* or *previous*.
        # data structures to build:
        # - versions: Dict[project, List[artifact]]
        # - current: Dict[project, artifact]
        for project in sorted(versions):
            artifacts = versions[project]

        # Then, loop over projects: sorted(versions.keys())
        #

        # <plugin> tag
        plugin = etree.SubElement(self.tree.getroot(), "plugin")
        plugin.set("filename", artifact.filename())

        # <platform> tag
        platform_string = deduce_platform(artifact.classifier)
        if platform_string:
            platform = etree.SubElement(plugin, "platform")
            platform.text = platform_string

        # <version> tag
        version = etree.SubElement(plugin, "version")
        checksum = artifact.md5() # main_artifact.sha1() # FIXME: use custom Updater checksum
        version.set("checksum", checksum)
        version.set("timestamp", timestamp(artifact.path))
        version.set("filesize", str(artifact.path.stat().st_size))

        # <description> tag
        pom = artifact.component.pom()
        desc = pom.description()
        if desc:
            description = etree.SubElement(version, "description")
            description.text = desc

        # <dependency> tags
        for dep in deps:
            dependency = etree.SubElement(version, "dependency")
            dependency.set("filename", "jars/ij.jar")
            dependency.set("timestamp", "20110203144124")

        # <author> tags
        # CTR FIXME: pom.developers, pom.contributors
        for author_name in authors:
            author = etree.SubElement(version, "author")
            author.text = author_name

        # <previous-version> tags
        # CTR FIXME: need maven-metadata.xml I guess
        # Need to build up a complete set of dependencies across all previous versions, in addition to only those for the current version.
        # every <plugin> is an artifact, which is reflected in the method sig.
        # every dependency is also translated into an artifact.
        # build up details in data structures (queue, set, and/or dict)
        # then call add_plugin recursively on the data structure.
        for pv in previous_versions:
            previous_version = etree.SubElement(plugin, "previous-version")
            previous_version.set("timestamp", "20110203214538")
            previous_version.set("timestamp-obsolete", "0")
            previous_version.set("checksum", "8dee3846e4ca1a0ad4169cf5e4859bcf52b878af")
            previous_version.set("filename", "plugins/3D_Blob_Segmentation.jar")
