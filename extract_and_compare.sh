#!/bin/bash

# usage: ./extract_and_compare.sh [input_before] [input_after] [media_id] {key}
# this script extracts a media id from both before and after the trimming,
# then calculates their MD5s to see if they are the same.
# 
# use the following sql query to get all media ids that span across multiple
# files (for edge case testing):
# 		select * from (select MapKey, count(DISTINCT(FileName)) as fc from MsgFileSegment GROUP BY MapKey) WHERE fc > 1;

id=$3
key=$4
fname="extracted_media_$id"
fname_before=${fname}_before.bin 
fname_after=${fname}_after.bin 
before_db="$1/Backup_decrypted.db"
after_db="$2/Backup_output_before_encrypt.db"
key_param=

if [ ! -z "$key" ]; then
	key_param="-k $key"
	before_db="$1/Backup.db"
	after_db="$2/Backup.db"
fi

rm -f $fname_before $fname_after

python extract_media.py --db $before_db --input $1 --id $id -o $fname_before $key_param
python extract_media.py --db $after_db --input $2 --id $id -o $fname_after $key_param

md5sum=md5
if ! command -v md5 &> /dev/null
then
	md5sum=md5sum
fi

ls -l $fname_before $fname_after
${md5sum} $fname_before $fname_after
