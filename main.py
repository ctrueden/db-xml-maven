import logging
import os
from pathlib import Path

import maven
from updater import FilesCollection

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
env = maven.Environment(local_repos=local_repos, remote_repos=remote_repos)

print("Initializing FilesCollection...")
fc = FilesCollection()

# Define the Maven artifact.
project = env.project("org.scijava", "scijava-common")
component = project.at_version("2.96.0")
#project = env.project("net.imagej", "imagej")
#component = project.at_version("2.14.0")
artifact = component.artifact()

#coords = [arg for arg in args if ":" in arg]
#for coord in coords:
#    print(f"Processing {coord}...")
#    tokens = coord.split(":")
#    g = tokens[0]
#    a = tokens[1]
#    project = env.project(g, a)
#    v = tokens[2] if len(tokens) > 2 else project.release
#    component = project.at_version(v)
#    fc.add_artifact(component.artifact())

print(f"Adding artifact {artifact}...")
fc.add_artifact(artifact)

print("Generating resultant XML...")
xml = fc.generate_xml("template.xml")
print(xml)
#with open(f"db-{g}-{a}-{v}.xml", "w") as f:
#    f.write(xml)
