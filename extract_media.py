import os
import sys
import utils
import hashlib
import argparse

def extract_media(con, input_dir, media_id, output_file):
	out = open(output_file, "bw")

	for (inneroffset,segmentlen,totallen,fileoffset,filename) in con.execute("select InnerOffSet,Length,TotalLen,OffSet,FileName from MsgFileSegment where MapKey = {} order by InnerOffSet asc;".format(media_id)):
		input = utils.get_input_media_file(os.path.join(input_dir, filename))
		input.seek(fileoffset, 0)
		out.seek(inneroffset, 0)
		out.write(input.read(segmentlen))

	out.close()

if __name__ == '__main__':
	# usage: python extract_media.py {media_id}

	# this script extracts a media id from both before and after the trimming,
	# then calculates their MD5s to see if they are the same.
	# 
	# use the following sql query to get all media ids that span across multiple
	# files (for edge case testing):
	# 		select * from (select MapKey, count(DISTINCT(FileName)) as fc from MsgFileSegment GROUP BY MapKey) WHERE fc > 1;

	parser = argparse.ArgumentParser(prog='extract_media')

	parser.add_argument("--id", required=True)
	parser.add_argument("--db", required=True)
	parser.add_argument("--input", required=True)
	parser.add_argument("--output_file", "-o", required=True)
	parser.add_argument("-k", "--key")

	args = parser.parse_args()

	KEY = args.key

	if KEY is not None:
		import pysqlcipher3.dbapi2 as sqlite3
	else:
		import sqlite3

	media_id = int(args.id)

	con = sqlite3.connect(args.db)
	con.execute("pragma query_only = ON;")
	if KEY is not None:
		utils.setup_sqlcipher_param(con, KEY)

	extract_media(con, args.input, media_id, args.output_file)
	
	con.close()