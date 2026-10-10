# 实体层：rules 包用到的固定值。不依赖 AstrBot，也不访问数据库。

# rules 包里的功能共用一个 SQLite 文件，各自用一张表。
# 关键词、触发词、验证 pending 等业务行放这个库；功能开没开改走 WebUI 群号名单。
DB_FILE_NAME = "rules.db"

# WebUI：每个功能一份开启群号名单。空名单即关，不兼容旧的 SQLite 开关表。
CFG_KEYWORD_GROUPS = "keyword_groups"
CFG_FORBIDDEN_GROUPS = "forbidden_groups"
CFG_WELCOME_GROUPS = "welcome_groups"
CFG_VERIFY_GROUPS = "verify_groups"
CFG_INVITE_GROUPS = "invite_groups"

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
# WebUI 关键词表默认每页条数。
KEYWORD_PAGE_SIZE = 20

# 读不到 AstrBot 真实配置时的兜底唤醒前缀。AstrBot 自己的默认值也是 /。
DEFAULT_WAKE_PREFIX = "/"

# 群里直接发的管理命令。不走 AstrBot 指令过滤器，所以不需要唤醒前缀。
# 功能开/关已迁到 WebUI 群号名单，群里不再认「开」「关」。
CMD_WELCOME_SET = "欢迎语 设置"
CMD_WELCOME_SHOW = "欢迎语"


# 上线链最多往上追几层。出现环或超过就截断，避免死循环。
INVITE_UPLINE_LIMIT = 20
# 整条下线一次最多列出多少人。超出的只报数量，不刷屏。
INVITE_DOWNLINE_LIMIT = 30

# 欢迎语文案长度上限。够写一段入群说明，避免误贴整篇文章。
WELCOME_MAX_LEN = 500
# WebUI 欢迎语表默认每页条数。
WELCOME_PAGE_SIZE = 20
# WebUI：没单独设过的开启群用这句全局文案。留空则用默认句。
CFG_WELCOME_TEXT = "welcome_text"
# 开了名单但还没填文案时，入群发送这句。沿用旧 GroupWelcome 的默认句。
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
# WebUI 触发词表默认每页条数。
FORBIDDEN_TRIGGER_PAGE_SIZE = 20

# 违禁词禁言秒数没填时的默认值。WebUI 可改。
DEFAULT_FORBIDDEN_MUTE_SECONDS = 60

# QQ 单次禁言上限 30 天。超过就夹到这个值，避免协议端直接拒绝。
MAX_FORBIDDEN_MUTE_SECONDS = 2592000

# OneBot 群成员 role。只有这两个才跳过违禁检测；读不到就当普通群员。
QQ_ROLE_OWNER = "owner"
QQ_ROLE_ADMIN = "admin"

# 插件 WebUI：准则单行，样本多行；触发词进 SQLite。
FORBIDDEN_CFG_GUIDELINE = "forbidden_guideline"
FORBIDDEN_CFG_SAMPLES = "forbidden_samples"
FORBIDDEN_CFG_MUTE_SECONDS = "forbidden_mute_seconds"
FORBIDDEN_CFG_REMIND_TEXT = "forbidden_remind_text"
FORBIDDEN_CFG_FEISHU_WEBHOOK = "forbidden_feishu_webhook"
# WebUI：文本路额外触发。开了就把这类内容当命中触发词，再送模型。默认全关。
FORBIDDEN_CFG_TRIGGER_URL = "forbidden_trigger_url"
FORBIDDEN_CFG_TRIGGER_GROUP = "forbidden_trigger_group"
FORBIDDEN_CFG_TRIGGER_QQ = "forbidden_trigger_qq"
FORBIDDEN_CFG_TRIGGER_PHONE = "forbidden_trigger_phone"
FORBIDDEN_CFG_TRIGGER_WECHAT = "forbidden_trigger_wechat"
# 规则触发写进日志/飞书的名字，当触发词用。
FORBIDDEN_PATTERN_URL = "网址"
FORBIDDEN_PATTERN_GROUP = "群号"
FORBIDDEN_PATTERN_QQ = "QQ号"
FORBIDDEN_PATTERN_PHONE = "手机号"
FORBIDDEN_PATTERN_WECHAT = "微信号"

# WebUI：要拦截群名片的群号名单，按条添加。没写的群不拦。
FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS = "forbidden_block_group_card_groups"
# 飞书和处置日志里的触发名，不是用户正文，避免把卡片 JSON 里的签名带出去。
GROUP_CARD_HIT = "群名片"
# 违禁日志原因码。人话在业务层拼，飞书仍用短通知。
FORBIDDEN_REASON_MODEL = "model"
FORBIDDEN_REASON_GROUP_CARD = "group_card"
FORBIDDEN_REASON_QRCODE = "qrcode"
FORBIDDEN_REASON_IMAGE_MODEL = "image_model"
# 飞书和日志里的二维码触发名。
QRCODE_HIT = "图片含二维码"
# 飞书和日志里的图片转写触发名。不是用户正文。
IMAGE_TRANSCRIPT_HIT = "图片转写"
# 模型第二行原因上限，避免飞书被长文刷屏。
FORBIDDEN_JUDGE_REASON_MAX = 40
# 违禁命中后拉群历史的条数。只撤回这 30 条里该用户的消息。
FORBIDDEN_RECALL_HISTORY_COUNT = 30


# WebUI 日志表默认每页条数。
FORBIDDEN_LOG_PAGE_SIZE = 20

# 违禁：短视频抽帧固定值。时长单位是秒，大小单位是字节。
# 4.0 秒含边界，超过就不抽帧：伪造截图录屏通常 3 到 4 秒，再长会拖慢热路径。
SHORT_VIDEO_MAX_SECONDS = 4.0
# 时长不足 0.8 秒只抽 1 帧：这么短的视频只有一屏内容，多抽也是同一画面。
SHORT_VIDEO_FRAME_SPLIT_SHORT = 0.8
# 时长不足 2.0 秒抽 2 帧，达到 2.0 秒抽 3 帧：2 秒内画面变化少，2 帧够看。
SHORT_VIDEO_FRAME_SPLIT_MID = 2.0
# 单段短视频的抽帧数上限，与下面的等分兜底比例键对齐。
SHORT_VIDEO_MAX_FRAMES = 3
# 随机抽帧点避开首尾各 5%：首尾常见黑场和渐变，抽出来多半不是内容。
SHORT_VIDEO_SAMPLE_MARGIN = 0.05
# 相邻抽帧点的最小间隔占时长比例 1/6：3 个点正好铺满，避免全挤在同一秒。
SHORT_VIDEO_MIN_GAP_RATIO = 1 / 6
# 随机点排不开时的重抽次数上限：重抽 8 次还不行就改等分点，不能一直循环。
SHORT_VIDEO_RANDOM_TRIES = 8
# 随机点排不开时按帧数取的等分兜底比例，键是帧数，值是占时长的比例。
# 1 帧取 50%；2 帧取 25%、75%；3 帧取 20%、50%、80%。
SHORT_VIDEO_EVEN_RATIOS = {
    1: (0.5,),
    2: (0.25, 0.75),
    3: (0.2, 0.5, 0.8),
}
# 原始消息段 file_size 上限 20MB（20*1024*1024）。超过就不下载，省带宽和时间。
SHORT_VIDEO_MAX_FILE_BYTES = 20971520
# 单次 ffprobe 或单帧 ffmpeg 的超时秒数。超时就放弃该视频剩余帧，避免卡住热路径。
SHORT_VIDEO_TOOL_TIMEOUT_SECONDS = 8

# 图片检测测试：请求体解码后的图片字节上限 8MB（8*1024*1024），与页面校验一致。
IMAGE_TEST_MAX_BYTES = 8388608

# 本地引擎状态。二维码和 OCR 诊断共用这三个值，页面按它区分「没装」和「没检出」。
# ready 表示这次真的跑了识别；后两者表示没跑，检出必须报否。
ENGINE_READY = "ready"
ENGINE_MISSING = "missing"
ENGINE_INIT_FAILED = "init_failed"

# 入群验证：6 位数字码。入群立刻禁 30 天（QQ 上限）。WebUI 秒数字段仍保留，交码失败不再用它禁言。
VERIFY_CODE_LEN = 6
DEFAULT_VERIFY_MUTE_SECONDS = 2592000
VERIFY_CFG_MUTE_SECONDS = "verify_mute_seconds"
VERIFY_JOIN_MUTE_SECONDS = 2592000
# 群内提醒固定隔 2 小时。只在北京时间 8 点到 22 点发（含 8 点，不含 22 点）。
VERIFY_REMIND_INTERVAL_MINUTES = 120
VERIFY_REMIND_HOUR_START = 8
VERIFY_REMIND_HOUR_END = 22
# 白天到期提醒最多 4 次。已满 4 次再到期就踢出，不再发第 5 次码。入群说明不算这 4 次。
VERIFY_REMIND_MAX = 4
# 提醒循环大约隔多久扫一次到期 pending。不是每人一个任务。
VERIFY_REMIND_TICK_SECONDS = 20

# 注册插件 Page API 时用的插件名，必须和仓库目录名一致。
PLUGIN_NAME = "astrbot_plugin_w1ndys_rules"

# 18 个插件配置键按存储类型分组。schema 只在导入时读一次，之后 Pages 保存和热路径
# 都读 rules.db 的 plugin_setting，按这份分组决定怎么存。
SETTING_LIST_KEYS = (
    CFG_KEYWORD_GROUPS,
    CFG_FORBIDDEN_GROUPS,
    CFG_WELCOME_GROUPS,
    CFG_VERIFY_GROUPS,
    CFG_INVITE_GROUPS,
    FORBIDDEN_CFG_BLOCK_GROUP_CARD_GROUPS,
)
SETTING_TEXT_KEYS = (
    CFG_WELCOME_TEXT,
    FORBIDDEN_CFG_GUIDELINE,
    FORBIDDEN_CFG_SAMPLES,
    FORBIDDEN_CFG_REMIND_TEXT,
    FORBIDDEN_CFG_FEISHU_WEBHOOK,
)
SETTING_INT_KEYS = (
    FORBIDDEN_CFG_MUTE_SECONDS,
    VERIFY_CFG_MUTE_SECONDS,
)
SETTING_BOOL_KEYS = (
    FORBIDDEN_CFG_TRIGGER_URL,
    FORBIDDEN_CFG_TRIGGER_GROUP,
    FORBIDDEN_CFG_TRIGGER_QQ,
    FORBIDDEN_CFG_TRIGGER_PHONE,
    FORBIDDEN_CFG_TRIGGER_WECHAT,
)
# 布尔在 plugin_setting 里只有这两种写法。别的值读出来一律当 False。
SETTING_TRUE = "1"
SETTING_FALSE = "0"
