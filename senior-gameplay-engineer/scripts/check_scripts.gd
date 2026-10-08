extends SceneTree
## Loads every GDScript under res:// (skips addons/ and dot folders) so parse and type errors are printed.
## godot --headless --path <project> -s <this file>
## load() still returns a script when it has errors - read the "SCRIPT ERROR" lines (verify.py does).


func _initialize() -> void:
	var paths := _scripts("res://")
	for path in paths:
		ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
	print("[check_scripts] loaded %d scripts" % paths.size())
	quit()


func _scripts(dir: String) -> PackedStringArray:
	var out := PackedStringArray()
	for file in DirAccess.get_files_at(dir):
		if file.ends_with(".gd"):
			out.append(dir.path_join(file))
	for sub in DirAccess.get_directories_at(dir):
		if not sub.begins_with(".") and not (dir == "res://" and sub == "addons"):
			out.append_array(_scripts(dir.path_join(sub)))
	return out
