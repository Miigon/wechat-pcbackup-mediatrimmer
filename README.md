# wechat-pcbackup-mediatrimmer

## Background

总所周知，微信聊天记录备份功能非常容易中途中断，并且其断点续传功能非常垃圾：如果在备份一个会话的聊天记录的过程中，某个文件传输中途连接断开，那么微信并不会删除已经传输成功的数据片段。但是这时候如果重新开启传输，微信并不会复用原来已经存在的分片，而是从新从0开始传输该文件的所有分片。

这就使得，如果备份的聊天中含有较大的图片/视频/文件，并且传输在中途中断重启，将会产生比原消息记录更大甚至大数倍的备份文件，占用电脑空间。

本脚本解析备份文件数据库，并扫描过滤掉以下资源的分片：
 - 同一个资源内重复的分片
 - 传输未完成/不完整的资源
 - MediaID 重复/大小不一致的资源
 - 被您的自定义过滤规则过滤掉的（默认为空）

在此之后，本脚本会重新生成所有 `BAK_*_MEDIA` 文件，得到（hopefully）体积更小的备份文件。

> 技术细节：微信手机备份聊天记录到电脑过程中：图片、文件等资源会被切片、加密后存储在 `BAK_0_MEDIA`、`BAK_1_MEDIA`... 等一系列文件中（以 ~512KB 为最大大小做分片，每个 `BAK_*_MEDIA` 文件最大大小 1GB-2GB 不等），并且在 `Backup.db` 数据库的 `MsgFileSegment` 表记录这些切片并分配 MediaID（存储在 `MsgMedia` 表）。  
> 恢复数据过程则为：从 `Backup.db` 数据库中的 `MsgMedia` 表查到 MediaID，并通过 MediaID 在 `MsgFileSegment` 中找到该资源文件各个片段，以及所对应的 `BAK_*_MEDIA` 文件的位置以及大小，读取并拼接得到原始文件。

## Usage

本脚本除 python3 以外无特殊依赖。

### 使用 pysqlcipher3

如果你的平台是 macOS 或者其他可以比较方便安装 libsqlcipher 的平台，建议使用本方法。
使用你的平台支持的方式安装 libsqlcipher，例：
```bash
# macOS
brew install sqlcipher
# debian/ubuntu
sudo apt install sqlcipher
# fedora/centos
sudo dnf install sqlcipher
```

然后，安装 pysqlcipher3。
```bash
pip install pysqlcipher3
```

安装成功后，跟随以下步骤：

1. (可选, 推荐) 运行 `python media_trimmer.py -i [备份目录] [Backup.db密钥]`，查看碎片和重复片段数量（dry-run，如果不是特别多的话建议不用清理）
2. 运行成功后，`./output` 文件夹下产生输出的 `BAK_*_MEDIA` 文件以及 `Backup.db` 数据库文件（已加密）
3. _(非必需) 运行 `./extract_and_compare.sh [备份目录] ./output [任意MediaID] [Backup.db密钥]`，该工具将分别从原始备份以及处理后的输出备份中分别提取指定 MediaID 的资源文件，并分别计算 MD5，校验处理前后数据是否一致。_
4. 移走/删除微信备份文件夹下的所有多余 `BAK_*_MEDIA` （注意备份！注意不要误删 `BAK_*_TEXT`）
5. 将 `./output` 文件夹下 `Backup.db` 以及所有新 `BAK_*_MEDIA` 替换到微信备份文件夹下
6. 重新登陆电脑端微信，测试恢复聊天记录（重点关注图片/文件等资源）

### 手动加解密

为了不引入对 sqlcipher 的依赖，本脚本支持您自行提前解密过的 `Backup.db` 文件，并在执行完成后自行以相同参数和密钥手动重新加密输出文件。  
这样做的话，不需要安装任何依赖就可以运行本脚本。

加解密方式以及密钥获得方式，不同平台可能存在差异。这里不详述，请参考互联网上的方法。操作前请注意备份，建议在副本上操作。

1. 手工解密 `Backup.db` 数据库（用 key 和正确参数打开并更改 key 为空），并**另存为 `Backup_decrypted.db`**. (置于 Backup.db 同目录下)
2. (可选, 推荐) 运行 `python media_trimmer.py -i [备份目录]`，查看碎片和重复片段数量（dry-run，如果不是特别多的话建议不用清理）
3. 运行 `python media_trimmer.py -i [备份目录] -o ./output --no-dry`，等待构建输出
4. 运行成功后，`./output` 文件夹下产生输出的 `BAK_*_MEDIA` 文件以及 `Backup_output_before_encrypt.db` 数据库文件
5. _(非必需) 运行 `./extract_and_compare.sh [备份目录] ./output [任意MediaID]`，该工具将分别从原始备份以及处理后的输出备份中分别提取指定 MediaID 的资源文件，并分别计算 MD5，校验处理前后数据是否一致。_
6. 将数据库文件 `Backup_output_before_encrypt.db` 重新以 **【相同加密参数及密钥】** 加密，得到输出 `Backup.db`
7. 移走/删除微信备份文件夹下的所有多余 `BAK_*_MEDIA` （注意备份！注意不要误删 `BAK_*_TEXT`）
8. 将新 `Backup.db` 以及 `./output` 文件夹下的所有新 `BAK_*_MEDIA`，替换到微信备份文件夹下
9. 重新登陆电脑端微信，测试恢复聊天记录（重点关注图片/文件等资源）

## 样例输出

这是我自己的一个用了4年左右的聊天记录备份，期间增量备份过4次，每次增量备份都有较多失败重试：

```
key provided, use sqlcipher. make sure libsqlcipher is installed
mode: NON-dry-run!! result data will be written to ./output
connecting to output db: ./output/Backup.db
writing to output file: BAK_0_MEDIA
writing to output file: BAK_1_MEDIA
......
writing to output file: BAK_25_MEDIA
writing to output file: BAK_26_MEDIA
DB: freed 38759 dangling media ids
DB: vacuumming...
====== stats ======
filtered media:
        incomplete media count: 38757  (1128.01 MiB)
        inconsistently sized media count: 2  (16.87 MiB)
        media with holes: 0  (0.00 MiB)
        custom filtered media: 0  (0.00 MiB)
segment dedup:
        media with duplicated segments: 81718
        dedup total size cut: 121803.54 MiB (68.19% cut)
results:
        before size: 174.44 GiB
        after size: 53.27 GiB
        media count: 325536 -> 286777 (88.09%)
        segment count: 828886 -> 360369 (43.48%)
```

通过删除重复片段以及无效文件，将备份文件从 174.44 GiB 降到了 53.27 GiB。

这里是比较极端的样例。其中有一个800MB的文件重复了数十次。

## Disclaimer

本脚本仅在 macOS 版微信 3.8.4 下测试通过。

不保证脚本不会造成数据损坏！请自行测试并多做备份，本脚本作者不承担使用此脚本造成的任何数据损坏与丢失的责任。
