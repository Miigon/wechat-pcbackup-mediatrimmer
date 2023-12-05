import io

input_media_file = {}
def get_input_media_file(path: str) -> io.BufferedReader:
	global input_media_file
	if input_media_file.get(path) is None:
		input_media_file[path] = open(path, "br")
	return input_media_file[path]