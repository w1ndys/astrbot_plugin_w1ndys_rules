# 实体层：rules 包用到的固定值。不依赖 AstrBot，也不访问数据库。

# rules 包里的功能共用一个 SQLite 文件，各自用一张表。
# 群开关、关键词都放在这个库里，方便一起备份。
DB_FILE_NAME = "rules.db"

# 包内功能键。群开关按「群号 + 功能键」记录，以后加功能时在这里追加。
FEATURE_KEYWORD = "keyword"
FEATURE_FORBIDDEN = "forbidden"
FEATURE_WELCOME = "welcome"

# 旧黑名单用这个 group_id 表示全局名单，群名单用真实群号。
BLACKLIST_GLOBAL_SCOPE = "global"

# 列黑名单时，超过这个人数就发合并转发，避免刷屏。不超过则把全文交给模型转述。
BLACKLIST_LIST_LIMIT = 30

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
CMD_WELCOME_ON = "欢迎语 开"
CMD_WELCOME_OFF = "欢迎语 关"
CMD_WELCOME_SET = "欢迎语 设置"
# 整句相等才查当前文案，避免把「欢迎语 开」当成查询
CMD_WELCOME_SHOW = "欢迎语"

# 欢迎语文案长度上限。够写一段入群说明，避免误贴整篇文章。
WELCOME_MAX_LEN = 500

# 开了开关但还没设文案时，入群发送这句。沿用旧 GroupWelcome 的默认句。
DEFAULT_WELCOME_TEXT = "欢迎入群~"

# 违禁配置条目类型。触发词决定是否送模型；样本已改回 WebUI，库表仍保留 kind 字段。
FORBIDDEN_KIND_TRIGGER = "trigger"
FORBIDDEN_KIND_SAMPLE = "sample"

# 触发词全局共用，不再按群隔离。写入和读取都用这个固定键。
FORBIDDEN_GLOBAL_SCOPE = "*"

# 单条违禁触发词的长度上限，避免误粘贴整篇文本长期占用快照。
FORBIDDEN_ITEM_MAX_LEN = 500

# 查询时一次最多返回多少条，超出只报告剩余数量，避免刷屏。
FORBIDDEN_LIST_LIMIT = 30

# 违禁词禁言秒数没填时的默认值。WebUI 可改。
DEFAULT_FORBIDDEN_MUTE_SECONDS = 60

# QQ 单次禁言上限 30 天。超过就夹到这个值，避免协议端直接拒绝。
MAX_FORBIDDEN_MUTE_SECONDS = 2592000

# OneBot 群成员 role。只有这两个才跳过违禁检测；读不到就当普通群员。
QQ_ROLE_OWNER = "owner"
QQ_ROLE_ADMIN = "admin"

# 近几天在本群发过言的人跳过违禁模型，少消耗、少误伤熟人。没记录或超窗仍送模型。
ACTIVE_WINDOW_DAYS = 7

# 插件 WebUI：准则单行，样本多行；触发词进 SQLite。
FORBIDDEN_CFG_GUIDELINE = "forbidden_guideline"
FORBIDDEN_CFG_SAMPLES = "forbidden_samples"
FORBIDDEN_CFG_MUTE_SECONDS = "forbidden_mute_seconds"
FORBIDDEN_CFG_REMIND_TEXT = "forbidden_remind_text"
FORBIDDEN_CFG_FEISHU_WEBHOOK = "forbidden_feishu_webhook"

# 注册插件 Page API 时用的插件名，必须和仓库目录名一致。
PLUGIN_NAME = "astrbot_plugin_w1ndys_rules"
