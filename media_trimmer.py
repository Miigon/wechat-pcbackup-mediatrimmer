import sqlite3
import os
import shutil
import utils

KB = 1024
MB = KB*1024
GB = MB*1024

input_dir = "./input/"
input_db_decrypted = "Backup_decrypted.db"
output_dir = "./output/"
output_db_name = "Backup_output_before_encrypt.db" # within output_dir

output_db = os.path.join(output_dir, output_db_name)

shutil.rmtree(output_dir, ignore_errors=True)
os.mkdir(output_dir)

shutil.copyfile(input_db_decrypted, output_db, follow_symlinks=True)

con = sqlite3.connect(input_db_decrypted)
con.execute("pragma query_only = ON;")
conout = sqlite3.connect(output_db)

conout.execute("delete from MsgFileSegment;")
conout.commit()

EXPORT_FILE_SIZE_LIMIT = 2*GB
DEBUG = False

def dprint(*values):
	if DEBUG:
		print(*values)

stat_inconsistent_cnt = 0
stat_incomplete_media = 0
stat_incomplete_bytes = 0
stat_media_with_holes = 0
stat_media_with_dup = 0
stat_dedup_bytes_cut = 0
stat_allblock_total_bytes = 0
stat_result_bytes = 0
(stat_initial_block_cnt,) = con.execute("select count(*) from MsgFileSegment;").fetchone()
(stat_initial_media_cnt,) = con.execute("select count(distinct(MapKey)) from MsgFileSegment;").fetchone()
stat_result_media_cnt = 0
stat_result_block_cnt = 0

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
	print("writing to output file:", cur_output_file_name)
	return open(os.path.join(output_dir, cur_output_file_name), "bw")


cur_output_file = open_output_media_file(0)

media_cnt = 0
for (i,) in con.execute("select DISTINCT(MapKey) key from MsgFileSegment order by key;"):
	media_cnt += 1
	reslength = -1 # total resource length as reported by TotalLen column
	totalblocklen = 0 # total size of all the blocks found (counting duplicate bytes)
	valid_len = 0 # length of consecutive valid bytes already found (not counting duplicate bytes)
	holes = 0
	inconsistently_sized = False
	used_blocks = []
	for (inneroffset,blocklen,totallen,fileoffset,filename) in con.execute("select InnerOffSet,Length,TotalLen,OffSet,FileName from MsgFileSegment where MapKey = {} order by InnerOffSet asc;".format(i)):
		totalblocklen += blocklen
		if reslength == -1:
			reslength = totallen
		elif reslength != totallen or inconsistently_sized: # reslength changed mid-way
			inconsistently_sized = True
			# delibrately not breaking, just to continue counting stats.
			continue
		if inneroffset > valid_len:
			holes += 1
			dprint("media id {}: hole in range [{}, {}]".format(i, valid_len, inneroffset-1))
		if inneroffset + blocklen <= valid_len:
			# duplicated/fully-overlapped block that provides no new data
			continue
		# valid new block
		valid_len = inneroffset + blocklen
		used_blocks.append((inneroffset, blocklen, fileoffset, filename))

	stat_allblock_total_bytes += totalblocklen

	if inconsistently_sized:
		stat_inconsistent_cnt += 1
		dprint("media id {} skipped: reslength inconsistent between blocks: {} -> {}".format(i, reslength, totallen))
		continue
	if holes > 0:
		stat_media_with_holes += 1
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
	if valid_len < reslength:
		stat_incomplete_media += 1
		stat_incomplete_bytes += valid_len
		dprint("media id {} skipped since it's not complete ({}/{} bytes)".format(i, valid_len, reslength))
		continue
	stat_dedup_bytes_cut += totalblocklen - reslength
	cut_rate = (1-reslength/totalblocklen)*100
	if cut_rate != 0:
		stat_media_with_dup += 1
		dprint("media {} cut by {:.1f}%".format(i, cut_rate))
	stat_result_bytes += reslength
	
	# write media to file
	stat_result_media_cnt += 1
	cur_inneroffset = 0
	new_blocks = []
	for (inneroffset, blocklen, fileoffset, srcfile) in used_blocks:
		if inneroffset < cur_inneroffset: # new block's range partially overlap with previous block(s)
			overlap = cur_inneroffset - inneroffset
			inneroffset += overlap
			fileoffset += overlap
			blocklen -= overlap
			print("partially overlapped block for media {}: overlap {} bytes".format(i, overlap))
		# copy [fileoffset, blocklen] from srcfile to output media file.
		input = utils.get_input_media_file(os.path.join(input_dir, srcfile))
		input.seek(fileoffset, 0)
		newfileoffset = cur_file_size
		cur_output_file.write(input.read(blocklen)) ## comment out this line to disable writing the actual BAK_*_MEDIA files 
		new_blocks.append((inneroffset, blocklen, newfileoffset, cur_output_file_name))
		cur_inneroffset += blocklen
		cur_file_size += blocklen
		if cur_file_size >= EXPORT_FILE_SIZE_LIMIT:
			# create and open a new media file for future blocks
			cur_output_file.close()
			cur_output_file = open_output_media_file(cur_file_id + 1)

	for (inneroffset, blocklen, fileoffset, filename) in new_blocks:
		stat_result_block_cnt += 1
		conout.execute(
			"INSERT INTO MsgFileSegment (MapKey, InnerOffSet, Length, TotalLen, OffSet, Reserved1, FileName, Reserved4) VALUES (?, ?, ?, ?, ?, 0, ?, 0);",
			(i, inneroffset, blocklen, reslength, fileoffset, filename)
		)

conout.commit()

if cur_output_file is not None:
	cur_output_file.close()
	cur_output_file = None

# delete dangling MediaIds in MsgMedia now that some of the MediaIds are completely gone.

freed_mediaids = conout.execute("delete from MsgMedia where MediaId in (select MediaId from MsgMedia where MediaId not in (select MapKey from MsgFileSegment));").rowcount
conout.commit()

print("DB: freed {} dangling media ids".format(freed_mediaids))

print("DB: vacuumming...")

conout.execute("VACUUM;")

print("====== stats ======")
print("incomplete media count:", stat_incomplete_media, " (~{:.2f} MiB)".format(stat_incomplete_bytes/MB))
print("inconsistently sized media count:", stat_inconsistent_cnt)
print("media with holes:", stat_media_with_holes)
print("-------------------")
print("media with duplicated blocks:", stat_media_with_dup)
print("dedup total MiB cut: {:.2f}".format(stat_dedup_bytes_cut/MB))
print("dedup cut rate (%): {:.2f}".format(stat_dedup_bytes_cut/stat_allblock_total_bytes * 100))
print("before size GiB: {:.2f}".format(stat_allblock_total_bytes/GB))
print("after size GiB: {:.2f}".format(stat_result_bytes/GB))
print("media count: {} -> {}".format(stat_initial_media_cnt, stat_result_media_cnt))
print("block count: {} -> {}".format(stat_initial_block_cnt, stat_result_block_cnt))

con.close()
conout.close()