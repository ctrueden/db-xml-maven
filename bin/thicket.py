#!/usr/bin/env python

"""
Generate a complex collection of parent POMs and BOMs, and a project
that inherits from them. The goal is to better understand how Maven POM
interpolation works, and test the correctness of jgo's implementation.
"""

import random
import sys

from lxml import etree

# -- Constants --

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


def generate_pom(name, ancestor_count=ANCESTOR_COUNT, depth=0):
    root = etree.fromstring(TEMPLATE)
    if ancestor_count > 0:
        parent = create_child(root, "parent")
        create_child(parent, "groupId", GROUP_ID)
        create_child(parent, "artifactId", f"{name}-parent{ancestor_count}")
        create_child(parent, "version", random_version())
        for a in range(ancestor_count - 1, 0, -1):
            generate_pom(f"{name}-parent{a}", ancestor_count=a, depth=depth+1)

    bom_count = min(MAX_IMPORTS - depth, random.randint(0, MAX_IMPORTS))
    dep_mgmt = create_child(root, "dependencyManagement")
    dep_mgmt_deps = create_child(dep_mgmt, "dependencies")
    for a in range(bom_count):
        dep = create_child(dep_mgmt_deps, "dependency")
        create_child(dep, "groupId", GROUP_ID)
        create_child(dep, "artifactId", f"{name}-bom{a}")
        # FIXME: sometimes use properties... think about how best to randomize that
        # - sometimes we want to define the property also in this POM, sometimes not.
        # - sometimes we want to add an explicit version element override here, sometimes not.
        create_child(dep, "version", random_version())
        create_child(dep, "type", "pom")
        create_child(dep, "scope", "import")
        generate_pom(f"{name}-bom{a}", ancestor_count=ancestor_count, depth=depth)

    # START HERE - randomly add some managed dependencies here!
    # randomize scope of these as well

    # TODO: add dependencies

    return root


def main(args):
    root = generate_pom("thicket")
    xml = etree.tostring(root, xml_declaration=True, encoding="utf-8").decode()
    print(xml)


if __name__ == "__main__":
    main(sys.argv[1:])
