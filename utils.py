import io

input_media_file = {}
def get_input_media_file(path: str) -> io.BufferedReader:
	global input_media_file
	if input_media_file.get(path) is None:
		input_media_file[path] = open(path, "br")
	return input_media_file[path]

def setup_sqlcipher_param(con, key):
	con.execute("PRAGMA key = '{}';".format(key))
	con.execute("pragma kdf_iter = 64000;")
	con.execute("pragma cipher_page_size = 4096;")
	con.execute("pragma cipher_hmac_algorithm = HMAC_SHA1;")
	con.execute("pragma cipher_kdf_algorithm = PBKDF2_HMAC_SHA1;")
	try:
		con.execute("select count(*) from sqlite_master;")
	except sqlite3.DatabaseError as e:
		print("db error: [", e, "], incorrect key?")
		sys.exit(-1)
	return