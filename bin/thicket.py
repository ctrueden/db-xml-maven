#!/usr/bin/env python

"""
Generate a complex collection of parent POMs and BOMs, and a project
that inherits from them. The goal is to better understand how Maven POM
interpolation works, and test the correctness of jgo's implementation.
"""

import random
import sys
from pathlib import Path

from lxml import etree

# -- Constants --

OUTPUT_DIR = Path("thicket")
TEMPLATE: bytes = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" \
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" \
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
\t<modelVersion>4.0.0</modelVersion>
</project>
""".encode("UTF-8")

# for l in a b c d e f g h i j k l m n o p q r s t u v w x y z
# do
# grep "^$l.\{4\}" google-10000-english-usa-no-swears.txt | grep -v '.\{8\}' | shuf | head -n1
# done
NAMES = {
    "active", "bullet", "coral", "detail", "essence", "fonts", "games",
    "heating", "ignore", "journal", "knives", "lodge", "major", "neutral",
    "optics", "permits", "quoted", "rotary", "socket", "tickets", "upload",
    "vendors", "weight", "xhtml", "younger", "zoning",
}

GROUP_ID = "org.scijava.jgo.thicket"
ANCESTOR_COUNT = 5
MAX_IMPORTS = 3
MAX_DEPTH = 10


# -- Variables --

versions = set()


# -- Functions --

def create_child(element, tagname, text=None):
    child = etree.SubElement(element, tagname)
    if text: child.text = text
    return child


def random_version() -> str:
    assert len(versions) < 9999
    v = random.randint(0, 9999)
    while v in versions:
        v = random.randint(0, 9999)
    versions.add(v)
    return str(v)


def generate_pom(name, version=None, ancestor_count=ANCESTOR_COUNT, depth=0):
    root = etree.fromstring(TEMPLATE)
    if ancestor_count > 0:
        parent = create_child(root, "parent")
        parent_name = f"{name}-parent{ancestor_count}"
        v = random_version()
        create_child(parent, "groupId", GROUP_ID)
        create_child(parent, "artifactId", parent_name)
        create_child(parent, "version", v)
        create_child(parent, "relativePath")
        generate_pom(parent_name, version=v, ancestor_count=ancestor_count-1, depth=depth+1)
    else:
        create_child(root, "groupId", GROUP_ID)

    create_child(root, "artifactId", name)
    create_child(root, "version", version or random_version())

    bom_count = min(MAX_IMPORTS - depth, random.randint(0, MAX_IMPORTS))
    dep_mgmt = create_child(root, "dependencyManagement")
    dep_mgmt_deps = create_child(dep_mgmt, "dependencies")
    for a in range(bom_count):
        dep = create_child(dep_mgmt_deps, "dependency")
        bom_name = f"{name}-bom{a + 1}"
        create_child(dep, "groupId", GROUP_ID)
        create_child(dep, "artifactId", bom_name)
        # FIXME: sometimes use properties... think about how best to randomize that
        # - sometimes we want to define the property also in this POM, sometimes not.
        # - sometimes we want to add an explicit version element override here, sometimes not.
        v = random_version()
        create_child(dep, "version", v)
        create_child(dep, "type", "pom")
        create_child(dep, "scope", "import")
        generate_pom(bom_name, version=v, ancestor_count=ancestor_count, depth=depth+1)

    # START HERE - randomly add some managed dependencies here!
    # randomize scope of these as well

    # TODO: add dependencies

    with open((OUTPUT_DIR / name).with_suffix(".pom"), "w") as f:
        xml = etree.tostring(root, xml_declaration=True, pretty_print=True, encoding="utf-8").decode()
        f.write(xml)


# -- Main --

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_pom("thicket")
