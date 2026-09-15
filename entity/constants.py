# 实体层：rules 包用到的固定值。不依赖 AstrBot，也不访问数据库。

# rules 包里的功能共用一个 SQLite 文件，各自用一张表。
# 群开关、关键词都放在这个库里，方便一起备份。
DB_FILE_NAME = "rules.db"

# 包内功能键。群开关按「群号 + 功能键」记录，以后加功能时在这里追加。
FEATURE_KEYWORD = "keyword"

# 关键词长度上限。命中要求整条消息与关键词完全相等，太长没人会真的发出来，
# 只会白占内存快照。
KEYWORD_MAX_LEN = 100

# 回复文本长度上限。够写一段通知，又不至于被管理员误塞进一整篇文章。
REPLY_MAX_LEN = 500

# 列关键词时一次最多回多少条。超出的只报数量，不刷屏。
KEYWORD_LIST_LIMIT = 30

# 读不到 AstrBot 真实配置时的兜底唤醒前缀。AstrBot 自己的默认值也是 /。
DEFAULT_WAKE_PREFIX = "/"
