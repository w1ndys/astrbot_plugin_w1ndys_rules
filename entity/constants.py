# 实体层：rules 包用到的固定值。不依赖 AstrBot，也不访问数据库。

# rules 包里的功能共用一个 SQLite 文件，各自用一张表。
# 群开关、关键词都放在这个库里，方便一起备份。
DB_FILE_NAME = "rules.db"

# 包内功能键。群开关按「群号 + 功能键」记录，以后加功能时在这里追加。
FEATURE_KEYWORD = "keyword"
