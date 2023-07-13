from updater import FilesCollection
import maven

from pathlib import Path

# Define the Maven artifact.
remote_repos = {
    "scijava.public": "https://maven.scijava.org/content/groups/public"
}
print("Creating Maven environment...")
env = maven.Environment(remote_repos=remote_repos, resolver=maven.SysCallResolver(Path("mvn")))
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
