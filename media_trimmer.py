import os
import shutil
import utils
import sys
import argparse

def custom_media_filter(con, media_id, media_len):
	# NOTE: write your custom media filtering rule here.
	# eg. filter out files that are too large
	# if media_len > 100*MB:
	# 	return False
	return True

parser = argparse.ArgumentParser(prog='media_trimmer')

parser.add_argument("--no-dry", action='store_true')
parser.add_argument("--skip-copy", action='store_true', help="do not copy old data to new BAK_*_MEDIA files. (only build database.)")
parser.add_argument("--debug", action='store_true')
parser.add_argument("--input", "-i", default="./input")
parser.add_argument("--output", "-o", default="./output")
parser.add_argument("-k", "--key")

args = parser.parse_args()

DRY_RUN = not args.no_dry
SKIP_COPY = args.skip_copy
DEBUG = args.debug
KEY = args.key

if KEY is not None:
	print("key provided, use sqlcipher. make sure libsqlcipher is installed")
	import pysqlcipher3.dbapi2 as sqlite3
else:
	import sqlite3
	
def setup_db_conn(con):
	if KEY is not None:
		utils.setup_sqlcipher_param(con, KEY)	
	return con

KB = 1024
MB = KB*1024
GB = MB*1024

input_dir = args.input
output_dir = args.output
input_db_name = "Backup_decrypted.db"
output_db_name = "Backup_output_before_encrypt.db" # within output_dir
if KEY is not None:
	input_db_name = "Backup.db"
	output_db_name = "Backup.db"

input_db = os.path.join(input_dir, input_db_name)
output_db = os.path.join(output_dir, output_db_name)

if not DRY_RUN:
	if os.path.realpath(input_dir) == os.path.realpath(output_dir):
		print("input path and output path cannot be the same!")
		sys.exit(-1)
		
	if os.path.commonprefix([os.path.realpath(output_dir), os.path.realpath(".")]) == os.path.realpath(output_dir):
		print("output path cannot be the current path or parent path!")
		sys.exit(-1)

print(DRY_RUN and "mode: dry-run. nothing will be written. use --no-dry for an actual run" or ("mode: NON-dry-run!! result data will be written to "+output_dir))

if SKIP_COPY:
	print("skip copying data to BAK_*_MEDIA files. only build Backup.db")

if not DRY_RUN:
	shutil.rmtree(output_dir, ignore_errors=True)
	os.mkdir(output_dir)
	shutil.copyfile(input_db, output_db, follow_symlinks=True)

con = setup_db_conn(sqlite3.connect(input_db))
con.execute("pragma query_only = ON;")

if not DRY_RUN:
	global conout
	print("connecting to output db:", output_db)
	conout = setup_db_conn(sqlite3.connect(output_db))
	conout.execute("delete from MsgFileSegment;")
	conout.commit()

EXPORT_FILE_SIZE_LIMIT = 2*GB

def dprint(*values):
	if DEBUG:
		print(*values)

stat_inconsistent_media = 0
stat_inconsistent_media_bytes = 0
stat_incomplete_media = 0
stat_incomplete_bytes = 0
stat_media_with_holes = 0
stat_media_with_holes_bytes = 0
stat_media_with_dup = 0
stat_media_custom_filtered = 0
stat_media_custom_filtered_bytes = 0
stat_dedup_bytes_cut = 0
stat_allsegments_total_bytes = 0
stat_result_bytes = 0
(stat_initial_segment_cnt,) = con.execute("select count(*) from MsgFileSegment;").fetchone()
(stat_initial_media_cnt,) = con.execute("select count(distinct(MapKey)) from MsgFileSegment;").fetchone()
stat_result_media_cnt = 0
stat_result_segment_cnt = 0

cur_file_id = -1
cur_output_file_name = ""
cur_file_size = 0

def open_output_media_file(new_file_id):
	global cur_file_size
	global cur_file_id
	global cur_output_file_name
	cur_file_id = new_file_id
	cur_file_size = 0
	cur_output_file_name = "BAK_{}_MEDIA".format(new_file_id)
	if SKIP_COPY:
		print("skipped copy:", cur_output_file_name)
		return None
	print(DRY_RUN and "writing to output file (dry):" or "writing to output file:", cur_output_file_name)
	if DRY_RUN: return None
	return open(os.path.join(output_dir, cur_output_file_name), "bw")

cur_output_file = open_output_media_file(0)

media_cnt = 0
for (i,) in con.execute("select DISTINCT(MapKey) key from MsgFileSegment order by key;"):
	media_cnt += 1
	reslength = -1 # total resource length as reported by TotalLen column
	totalsegmentslen = 0 # total size of all the segments found (counting duplicate bytes)
	valid_len = 0 # length of consecutive valid bytes already found (not counting duplicate bytes)
	holes = 0
	inconsistently_sized = False
	used_segments = []
	for (inneroffset,segmentlen,totallen,fileoffset,filename) in con.execute("select InnerOffSet,Length,TotalLen,OffSet,FileName from MsgFileSegment where MapKey = {} order by InnerOffSet asc;".format(i)):
		totalsegmentslen += segmentlen
		if reslength == -1:
			reslength = totallen
		elif reslength != totallen or inconsistently_sized: # reslength changed mid-way
			inconsistently_sized = True
			# delibrately not breaking, just to continue counting stats.
			continue
		if inneroffset > valid_len:
			holes += 1
			dprint("media id {}: hole in range [{}, {}]".format(i, valid_len, inneroffset-1))
		if inneroffset + segmentlen <= valid_len:
			# duplicated/fully-overlapped segment that provides no new data
			continue
		# valid new segment
		valid_len = inneroffset + segmentlen
		used_segments.append((inneroffset, segmentlen, fileoffset, filename))

	stat_allsegments_total_bytes += totalsegmentslen

	if inconsistently_sized:
		stat_inconsistent_media += 1
		stat_inconsistent_media_bytes += totalsegmentslen
		dprint("media id {} skipped: reslength inconsistent between segments: {} -> {}".format(i, reslength, totallen))
		continue
	if holes > 0:
		stat_media_with_holes += 1
		stat_media_with_holes_bytes += totalsegmentslen
		dprint("media id {} skipped since it contains {} holes".format(i, holes))
		continue
	if valid_len < reslength:
		stat_incomplete_media += 1
		stat_incomplete_bytes += valid_len
		dprint("media id {} skipped since it's not complete ({}/{} bytes)".format(i, valid_len, reslength))
		continue
	if valid_len > reslength:
		raise RuntimeError("this really shouldn't happen.")
	# valid media

	# apply custom filter before trying to write this media to output
	if custom_media_filter(con, i, reslength) == False:
		dprint("custom filtered: ", i)
		stat_media_custom_filtered += 1
		stat_media_custom_filtered_bytes += totalsegmentslen
		continue

	stat_dedup_bytes_cut += totalsegmentslen - reslength
	cut_rate = (1-reslength/totalsegmentslen)*100
	if cut_rate != 0:
		stat_media_with_dup += 1
		dprint("media {} cut by {:.1f}%".format(i, cut_rate))
	stat_result_bytes += reslength
	
	# write media to file
	stat_result_media_cnt += 1
	cur_inneroffset = 0
	new_segments = []
	for (inneroffset, segmentlen, fileoffset, srcfile) in used_segments:
		if inneroffset < cur_inneroffset: # new segment's range partially overlap with previous segment(s)
			overlap = cur_inneroffset - inneroffset
			inneroffset += overlap
			fileoffset += overlap
			segmentlen -= overlap
			print("partially overlapped segment for media {}: overlap {} bytes".format(i, overlap))
		# copy [fileoffset, segmentlen] from srcfile to output media file.
		input = utils.get_input_media_file(os.path.join(input_dir, srcfile))
		input.seek(fileoffset, 0)
		newfileoffset = cur_file_size
		if not DRY_RUN and not SKIP_COPY: cur_output_file.write(input.read(segmentlen))
		new_segments.append((inneroffset, segmentlen, newfileoffset, cur_output_file_name))
		cur_inneroffset += segmentlen
		cur_file_size += segmentlen
		if cur_file_size >= EXPORT_FILE_SIZE_LIMIT:
			# create and open a new media file for future segments
			if not DRY_RUN and not SKIP_COPY: cur_output_file.close()
			cur_output_file = open_output_media_file(cur_file_id + 1)
	# write media segment info to db
	for (inneroffset, segmentlen, fileoffset, filename) in new_segments:
		stat_result_segment_cnt += 1
		if not DRY_RUN: conout.execute(
			"INSERT INTO MsgFileSegment (MapKey, InnerOffSet, Length, TotalLen, OffSet, Reserved1, FileName, Reserved4) VALUES (?, ?, ?, ?, ?, 0, ?, 0);",
			(i, inneroffset, segmentlen, reslength, fileoffset, filename)
		)

if not DRY_RUN: conout.commit()

if cur_output_file is not None:
	cur_output_file.close()
	cur_output_file = None

# delete dangling MediaIds in MsgMedia now that some of the MediaIds are completely gone.
if not DRY_RUN:
	freed_mediaids = conout.execute("delete from MsgMedia where MediaId in (select MediaId from MsgMedia where MediaId not in (select MapKey from MsgFileSegment));").rowcount
	conout.commit()
	print("DB: freed {} dangling media ids".format(freed_mediaids))

# recalculate total size for all sessions.
if not DRY_RUN:
	print("DB: recalculating TotalSize field for all sessions...")
	conout.execute("""
	update Session set TotalSize = (
	select (ifnull(t1.mediasize,0)+ifnull(t2.txtsize,0)) calc_size from Session s
	left join (select mm.talker talker, sum(mfs.Length) mediasize from MsgMedia mm inner join MsgFileSegment mfs on mm.MediaId = mfs.MapKey group by mm.talker) t1 on t1.talker = s.talker
	left join (select UsrName talker, sum(`Length`) txtsize from MsgSegments group by talker) t2 on t2.talker = s.talker
	where s.talker = Session.talker
	);
	""")
	conout.commit()
	# NOTE: check result by running this sql query:
	#
	# select *, (calc_mediasize+calc_txtsize) calc_totalsize, calc_mediasize+calc_txtsize-totalsize_original reduction from (
	# select NickName, s.talker, TotalSize totalsize_original, ifnull(t1.mediasize,0) calc_mediasize, ifnull(t2.txtsize,0) calc_txtsize from Session s
	# left join (select mm.talker talker, sum(mfs.Length) mediasize from MsgMedia mm inner join MsgFileSegment mfs on mm.MediaId = mfs.MapKey group by mm.talker) t1 on t1.talker = s.talker
	# left join (select UsrName talker, sum(`Length`) txtsize from MsgSegments group by talker) t2 on t2.talker = s.talker
	# ) where reduction != 0 order by reduction asc;
	#
	# if 0 rows are returned, all TotalSize fields are correct.

# do a final vacuum
if not DRY_RUN:
	print("DB: vacuumming...")
	conout.execute("VACUUM;")

def format_size(b):
	return " ({:.2f} MiB)".format(b/MB)

print("====== stats ======")
print("filtered media:")
print("\tincomplete media count:", stat_incomplete_media, format_size(stat_incomplete_bytes))
print("\tinconsistently sized media count:", stat_inconsistent_media, format_size(stat_inconsistent_media_bytes))
print("\tmedia with holes:", stat_media_with_holes, format_size(stat_media_with_holes_bytes))
print("\tcustom filtered media:", stat_media_custom_filtered, format_size(stat_media_custom_filtered_bytes))
print("segment dedup:")
print("\tmedia with duplicated segments:", stat_media_with_dup)
print("\tdedup total size cut: {:.2f} MiB ({:.2f}% cut)".format(stat_dedup_bytes_cut/MB, stat_dedup_bytes_cut/stat_allsegments_total_bytes * 100))
print("results:")
print("\tbefore size: {:.2f} GiB".format(stat_allsegments_total_bytes/GB))
print("\tafter size: {:.2f} GiB".format(stat_result_bytes/GB))
print("\tmedia count: {} -> {} ({:.2f}%)".format(stat_initial_media_cnt, stat_result_media_cnt, stat_result_media_cnt/stat_initial_media_cnt * 100))
print("\tsegment count: {} -> {} ({:.2f}%)".format(stat_initial_segment_cnt, stat_result_segment_cnt, stat_result_segment_cnt/stat_initial_segment_cnt * 100))

con.close()
if not DRY_RUN: conout.close()