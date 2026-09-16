# 实体层：rules 包用到的固定值。不依赖 AstrBot，也不访问数据库。

# rules 包里的功能共用一个 SQLite 文件，各自用一张表。
# 群开关、关键词都放在这个库里，方便一起备份。
DB_FILE_NAME = "rules.db"

# 包内功能键。群开关按「群号 + 功能键」记录，以后加功能时在这里追加。
FEATURE_KEYWORD = "keyword"
FEATURE_FORBIDDEN = "forbidden"

# 关键词长度上限。命中要求整条消息与关键词完全相等，太长没人会真的发出来，
# 只会白占内存快照。
KEYWORD_MAX_LEN = 100

# 回复文本长度上限。够写一段通知，又不至于被管理员误塞进一整篇文章。
REPLY_MAX_LEN = 500

# 列关键词时一次最多回多少条。超出的只报数量，不刷屏。
KEYWORD_LIST_LIMIT = 30

# 一次批量导入最多接受多少条非空行。再多就整批拒绝，避免误粘贴把库撑爆。
KEYWORD_BATCH_MAX_LINES = 200

# 批量导入回报里，冲突和跳过最多各列多少条。超出的只报数量。
KEYWORD_BATCH_DETAIL_LIMIT = 10

# 读不到 AstrBot 真实配置时的兜底唤醒前缀。AstrBot 自己的默认值也是 /。
DEFAULT_WAKE_PREFIX = "/"

# 群里直接发的管理命令。不走 AstrBot 指令过滤器，所以不需要唤醒前缀。
# 开、关必须整条消息完全相等，避免把后面的闲聊当命令。
CMD_KEYWORD_ON = "关键词 开"
CMD_KEYWORD_OFF = "关键词 关"
CMD_KEYWORD_BATCH = "关键词 批量"
CMD_FORBIDDEN_ON = "违禁词 开"
CMD_FORBIDDEN_OFF = "违禁词 关"

# 违禁词禁言秒数没填时的默认值。WebUI 可改。
DEFAULT_FORBIDDEN_MUTE_SECONDS = 60

# QQ 单次禁言上限 30 天。超过就夹到这个值，避免协议端直接拒绝。
MAX_FORBIDDEN_MUTE_SECONDS = 2592000

# 插件 WebUI 里违禁词字段。不是 SQLite 业务表。
FORBIDDEN_CFG_TRIGGER_WORDS = "forbidden_trigger_words"
FORBIDDEN_CFG_SAMPLES = "forbidden_samples"
FORBIDDEN_CFG_GUIDELINE = "forbidden_guideline"
FORBIDDEN_CFG_MUTE_SECONDS = "forbidden_mute_seconds"
FORBIDDEN_CFG_REMIND_TEXT = "forbidden_remind_text"
FORBIDDEN_CFG_FEISHU_WEBHOOK = "forbidden_feishu_webhook"

# 注册插件 Page API 时用的插件名，必须和仓库目录名一致。
PLUGIN_NAME = "astrbot_plugin_w1ndys_rules"
