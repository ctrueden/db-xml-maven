#!/usr/bin/env python

from pathlib import Path
from datetime import datetime

from lxml import etree

import maven


class FilesCollection:

    def __init__(self):
        self.tree = None
        # CTR FIXME use SimpleResolver once it is implemented. And don't hardcode relative `mvn` executable either!
        self.env = maven.Environment(resolver=maven.SysCallResolver("mvn"))

    def load(self, path):
        with open(path) as f:
            self.tree = etree.parse(f)

    def save(self, path):
        xml = etree.tostring(self.tree, xml_declaration=True, encoding="utf-8").decode()
        with open(path, "w") as f:
            f.write(xml)

    def add_plugin(self, g, a, v):
        project = self.env.project(g, a)
        component = project.component(v)
        main_artifact = component.artifact()
        pom_artifact = component.pom()
        checksum = pom_artifact.md5() # artifact.sha1() # FIXME: custom Updater checksum

        plugin = etree.SubElement(self.tree.getroot(), "plugin")

        platform_string = None # win32, win64, macosx, linux32, linux64
        if platform_string:
            platform = etree.SubElement(plugin, "platform")
            platform.text = platform_string

        plugin.set("filename", main_artifact.filename())

        version = etree.SubElement(plugin, "version")
        version.set("checksum", pom.checksum())
        version.set("timestamp", pom.timestamp())
        version.set("filesize", str(main_artifact.filesize()))
        desc = pom.description()
        if desc:
            description = etree.SubElement(version, "description")
            description.text = desc
        for dep in deps:
            dependency = etree.SubElement(version, "dependency")
            dependency.set("filename", "jars/ij.jar")
            dependency.set("timestamp", "20110203144124")
        for author_name in authors:
            author = etree.SubElement(version, "author")
            author.text = author_name

        for pv in previous_versions:
            previous_version = etree.SubElement(plugin, "previous-version")
            previous_version.set("timestamp", "20110203214538")
            previous_version.set("timestamp-obsolete", "0")
            previous_version.set("checksum", "8dee3846e4ca1a0ad4169cf5e4859bcf52b878af")
            previous_version.set("filename", "plugins/3D_Blob_Segmentation.jar")


def timestamp(path: Path) -> str:
    """Get a timestamp string of the form YYYYMMDDhhmmss."""
    mtime = self.path().stat().st_mtime
    dt = datetime.fromtimestamp(mtime)
    return dt.strftime("%Y%m%d%H%M%S")

def filesize(path: Path) -> int:
    return path.stat().st_size

