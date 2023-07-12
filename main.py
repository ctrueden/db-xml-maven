from updater import FilesCollection

# Read in the starting template.
fc = FilesCollection()
fc.load("template.xml")

# Add the plugin entry.
fc.add_plugin(g="net.imagej", a="imagej", v="2.14.0")

# Write out the result.
fc.save("db-{g}-{a}-{v}.xml")

remote_repositories = {
"scijava.public": "https://maven.scijava.org/content/groups/public"
}
