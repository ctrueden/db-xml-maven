#!/usr/bin/env python

from lxml import etree

from . import maven


def add_plugin(pluginRecords, g, a, v):
    plugin = etree.SubElement(pluginRecords, "plugin")

    platform_string = None # win32, win64, macosx, linux32, linux64
    if platform_string:
        platform = etree.SubElement(plugin, "platform")
        platform.text = platform_string

    plugin.set("filename", filename)

    version = etree.SubElement(plugin, "version")
    version.set("checksum", pom.checksum())
    version.set("timestamp", pom.timestamp())
    version.set("filesize", str(pom.filesize()))
    desc = pom.description()
    if desc:
        description = etree.SubElement(version, "description")
        description.text = desc
    for dep in deps:
        dependency = etree.SubElement(version, "dependency")
        dependency.set("filename", "jars/ij.jar")
        dependency.set("timestamp", ="20110203144124")
    for author_name in authors:
        author = etree.SubElement(version, "author")
        author.text = author_name

    for pv in previous_versions:
        previous_version = etree.SubElement(plugin, "previous-version")
        previous_version.set("timestamp", "20110203214538")
        previous_version.set("timestamp-obsolete", "0")
        previous_version.set("checksum", "8dee3846e4ca1a0ad4169cf5e4859bcf52b878af")
        previous_version.set("filename", "plugins/3D_Blob_Segmentation.jar")


# -- Main --

# Read in the starting template.
with open("template.xml") as f:
    tree = etree.parse(f)

# Add the plugin entry.
g = "net.imagej"
a = "imagej"
v = "2.14.0"
pom = 
add_plugin(tree.getroot(), g=g, a=a, v=v)

# Write out the result.
xml = etree.tostring(tree, xml_declaration=True, encoding="utf-8").decode()
with open("db-{g}-{a}-{v}.xml", "w") as f:
    f.write(s)
