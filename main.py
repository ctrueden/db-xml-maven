from updater import FilesCollection
import maven

from pathlib import Path

# Create appropriate Maven environment.
storage = Path("/opt/sonatype-work/nexus/storage")
release_repos = ["releases", "thirdparty", "sonatype", "sonatype-s01", "central", "ome-releases"]
snapshot_repos = ["snapshots", "sonatype-snapshots", "sonatype-snapshots-s01", "ome-snapshots"]
local_repos = [repo for r in release_repos + snapshot_repos if (repo := storage / r).exists()]
remote_repos = {
    "scijava.public": "https://maven.scijava.org/content/groups/public"
}
print("Creating Maven environment...")
env = maven.Environment(local_repos=local_repos, remote_repos=remote_repos, resolver=maven.SysCallResolver(Path("mvn")))

# Define the Maven artifact.
project = env.project("net.imagej", "imagej")
component = project.at_version("2.14.0")
artifact = component.artifact()

print("Initializing FilesCollection...")
# Read in the starting template.
fc = FilesCollection()

print(f"Adding artifact {artifact}...")
# Add the plugin entry.
fc.add_artifact(artifact)

print("Generating resultant XML...")
# Write out the result.
xml = fc.generate_xml("template.xml")
print(xml)
#with open(f"db-{g}-{a}-{v}.xml", "w") as f:
#    f.write(xml)
