from updater import FilesCollection
import maven

# Define the Maven artifact.
remote_repos = {
    "scijava.public": "https://maven.scijava.org/content/groups/public"
}
env = maven.Environment(remote_repos=remote_repos, resolver=maven.SysCallResolver("mvn"))
project = env.project("net.imagej", "imagej")
component = project.component("2.14.0")
artifact = component.artifact()

# Read in the starting template.
fc = FilesCollection()
fc.load("template.xml")

# Add the plugin entry.
fc.add_plugin(artifact)

# Write out the result.
fc.save("db-{g}-{a}-{v}.xml")
