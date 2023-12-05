import sqlite3
import os
import sys
import utils
import hashlib


def extract_media(con, input_dir, media_id, output_file):
	out = open(output_file, "bw")

	for (inneroffset,segmentlen,totallen,fileoffset,filename) in con.execute("select InnerOffSet,Length,TotalLen,OffSet,FileName from MsgFileSegment where MapKey = {} order by InnerOffSet asc;".format(media_id)):
		input = utils.get_input_media_file(os.path.join(input_dir, filename))
		input.seek(fileoffset, 0)
		out.seek(inneroffset, 0)
		out.write(input.read(segmentlen))

	out.close()

def _filehash(file):
	with open(file, "rb") as f:
		file_hash = hashlib.md5()
		chunk = f.read(8192)
		while chunk:
			file_hash.update(chunk)
			chunk = f.read(8192)
	return file_hash.hexdigest()

if __name__ == '__main__':
	# usage: python extract_media.py {media_id}

	# this script extracts a media id from both before and after the trimming,
	# then calculates their MD5s to see if they are the same.
	# 
	# use the following sql query to get all media ids that span across multiple
	# files (for edge case testing):
	# 		select * from (select MapKey, count(DISTINCT(FileName)) as fc from MsgFileSegment GROUP BY MapKey) WHERE fc > 1;
	media_id = int(sys.argv[1])

	con = sqlite3.connect("Backup_decrypted.db")
	con2 = sqlite3.connect("./output/Backup_output_before_encrypt.db")
	con.execute("pragma query_only = ON;")
	con2.execute("pragma query_only = ON;")

	output_before = "extracted_media_{}_before.bin".format(media_id)
	output_after = "extracted_media_{}_after.bin".format(media_id)

	extract_media(con, "./input/", media_id, output_before)
	extract_media(con2, "./output/", media_id, output_after)
	
	print("MD5 ({}) = {}".format(output_before,_filehash(output_before)))
	print("MD5 ({}) = {}".format(output_after,_filehash(output_after)))

	con.close()
	con2.close()