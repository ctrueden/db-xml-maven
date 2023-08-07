#!/usr/bin/env python

"""
Generate a complex collection of parent POMs and BOMs, and a project
that inherits from them. The goal is to better understand how Maven POM
interpolation works, and test the correctness of jgo's implementation.
"""

import random
from pathlib import Path

from lxml import etree

# -- Constants --

OUTPUT_DIR = Path(".")
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
NAMES = [
    "active", "bullet", "coral", "detail", "essence", "fonts", "games",
    "heating", "ignore", "journal", "knives", "lodge", "major", "neutral",
    "optics", "permits", "quoted", "rotary", "socket", "tickets", "upload",
    "vendors", "weight", "xhtml", "younger", "zoning",
]

GROUP_ID = "org.scijava.jgo.thicket"
ANCESTOR_COUNT = 4
MAX_IMPORTS = 3
MAX_DEPTH = 8


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


def generate_pom(name, packaging=None, version=None, ancestor_count=ANCESTOR_COUNT, depth=0):
    # NB: The remove_blank_text=True option is needed to pretty-print the XML output:
    # https://lxml.de/FAQ.html#why-doesn-t-the-pretty-print-option-reformat-my-xml-output
    root = etree.fromstring(TEMPLATE, parser=etree.XMLParser(remove_blank_text=True))
    if ancestor_count > 0:
        parent = create_child(root, "parent")
        parent_name = f"{name}-parent{ancestor_count}"
        v = random_version()
        create_child(parent, "groupId", GROUP_ID)
        create_child(parent, "artifactId", parent_name)
        create_child(parent, "version", v)
        create_child(parent, "relativePath")
        generate_pom(parent_name, packaging="pom", version=v, ancestor_count=ancestor_count-1, depth=depth+1)
    else:
        create_child(root, "groupId", GROUP_ID)

    create_child(root, "artifactId", name)
    create_child(root, "version", version or random_version())
    if packaging: create_child(root, "packaging", packaging)

    bom_count = min(MAX_IMPORTS - depth, random.randint(0, MAX_IMPORTS))
    dep_mgmt = create_child(root, "dependencyManagement")
    dep_mgmt_deps = create_child(dep_mgmt, "dependencies")
    for i in range(bom_count):
        dep = create_child(dep_mgmt_deps, "dependency")
        bom_name = f"{name}-bom{i + 1}"
        create_child(dep, "groupId", GROUP_ID)
        create_child(dep, "artifactId", bom_name)
        # TODO: Sometimes use properties; sometimes allow the version to be managed.
        v = random_version()
        create_child(dep, "version", v)
        create_child(dep, "type", "pom")
        create_child(dep, "scope", "import")
        generate_pom(bom_name, packaging="pom", version=v, ancestor_count=ancestor_count, depth=depth+1)

    # Manage some dependencies.
    properties = None
    dep_count = random.randint(0, 5)
    deps = set(random.choices(NAMES, k=dep_count))
    for artifact_id in deps:
        dep = create_child(dep_mgmt_deps, "dependency")
        create_child(dep, "groupId", GROUP_ID)
        create_child(dep, "artifactId", artifact_id)
        # Sometimes use a property for the version, but other times not.
        # - Sometimes we want to define the property also in this POM, sometimes not.
        # - Sometimes we want to add an explicit version element override here, sometimes not.
        # TODO: Sometimes allow the version to be managed.
        v = random_version()
        use_property = random.choice((True, False))
        if use_property:
            if properties is None:
                properties = create_child(root, "properties")
            prop_tag = artifact_id + ".version"
            create_child(properties, prop_tag, v)
            v = "${" + prop_tag + "}"
        create_child(dep, "version", v)
        # TODO: Consider randomizing classifier and/or scope of these as well.

    with open((OUTPUT_DIR / name).with_suffix(".pom"), "w") as f:
        xml = etree.tostring(root, xml_declaration=True, pretty_print=True, encoding="utf-8").decode()
        f.write(xml)


# -- Main --

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_pom("thicket")
