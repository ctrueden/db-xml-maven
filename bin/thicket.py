#!/usr/bin/env python

"""
Generate a complex collection of parent POMs and BOMs, and a project
that inherits from them. The goal is to better understand how Maven POM
interpolation works, and test the correctness of jgo's implementation.
"""

import random

from lxml import etree

template: bytes = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
	<modelVersion>4.0.0</modelVersion>
</project>
""".encode("UTF-8")

# for l in a b c d e f g h i j k l m n o p q r s t u v w x y z
# do
# grep "^$l.\{4\}" google-10000-english-usa-no-swears.txt | grep -v '.\{8\}' | shuf | head -n1
# done
names = {
    "active", "bullet", "coral", "detail", "essence", "fonts", "games",
    "heating", "ignore", "journal", "knives", "lodge", "major", "neutral",
    "optics", "permits", "quoted", "rotary", "socket", "tickets", "upload",
    "vendors", "weight", "xhtml", "younger", "zoning",
}

versions = set()

groupId = "org.scijava.jgo.thicket"
ancestor_count = 5
max_imports = 3
max_depth = 10

def create_child(element, tagname, text=None):
	child = etree.SubElement(element, tagname)
	if text: child.text = text
	return child

def random_version():
	assert len(versions) < 9999
	v = random.nextint(0, 10000)
	while v in versions:
		v = random.nextint(0, 10000)
	versions.add(v)
	return v

def generate_pom(name, ancestor_count=5, depth=0):
    tree = etree.fromstring(template)
    if ancestor_count > 0:
        parent = create_child(tree.getroot(), "parent")
		create_child(parent, "groupId", groupId)
		create_child(parent, "artifactId", f"{name}-parent{ancestor_count}")
		create_child(parent, "version", random_version())
		for a in range(ancestor_count, 0, -1):
			generate_pom(f"{name}-parent{a}")

	bom_count = min(max_imports - depth, random.randint(0, max_imports))
	dep_mgmt = create_child(tree.getroot(), "dependencyManagement")
	dep_mgmt_deps = create_child(dep_mgmt, "dependencies")
	for a in range(bom_count):
		dep = create_child(dep_mgmt_deps, "dependency")
		create_child(dep, "groupId", groupId)
		create_child(dep, "artifactId", f"{name}-bom{a}")
		# FIXME: sometimes use properties... think about how best to randomize that
		# - sometimes we want to define the property also in this POM, sometimes not.
		# - sometimes we want to add an explicit version element override here, sometimes not.
		create_child(dep, "version", random_version())
		create_child(dep, "type", "pom")
		create_child(dep, "scope", "import")
		generate_pom(f"{name}-bom{a}")

	# START HERE - randomly add some managed dependencies here!
	# randomize scope of these as well

	# TODO: add dependencies

xml = etree.tostring(tree, xml_declaration=True, encoding="utf-8").decode()
print(xml)
