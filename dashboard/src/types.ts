// 页面层：后端接口返回的数据形状与列表行。字段名照 business 下各 *_page.py 的 row 写。

// 群名映射的一行：群号到群名。
export interface GroupNameItem {
  group_id: string;
  group_name: string;
}

// group-name/list 和 group-name/pull 的返回，形状相同。
export interface GroupNameListResponse {
  items: GroupNameItem[];
}

// 写操作统一只回报一句中文结果。
export interface MessageResponse {
  message: string;
}

// 关键词行：keyword/list 的一项。
export interface KeywordRow {
  group_id: string;
  keyword: string;
  reply: string;
}

// keyword/list 的分页返回。
export interface KeywordListResponse {
  items: KeywordRow[];
  total: number;
  page: number;
  page_size: number;
}

// 违禁触发词行：forbidden-trigger/list 的一项。
export interface ForbiddenTriggerRow {
  content: string;
}

// forbidden-trigger/list 的分页返回。
export interface ForbiddenTriggerListResponse {
  items: ForbiddenTriggerRow[];
  total: number;
  page: number;
  page_size: number;
}

// 欢迎语行：welcome/list 的一项。
export interface WelcomeRow {
  group_id: string;
  content: string;
}

// welcome/list 的分页返回。
export interface WelcomeListResponse {
  items: WelcomeRow[];
  total: number;
  page: number;
  page_size: number;
}

// 违禁日志行上的四个名单状态，和 business/whitelist.py 的 roster_flags 字段名一致。
export interface RosterFlags {
  whitelisted: boolean;
  global_whitelisted: boolean;
  group_blacklisted: boolean;
  global_blacklisted: boolean;
}

// 违禁日志列表行：不含原文、JSON 段和图片。
export interface ForbiddenLogRow extends RosterFlags {
  id: number;
  group_id: string;
  user_id: string;
  sender_name: string;
  reason_code: string;
  reason_text: string;
  created_at: string;
}


// forbidden-log/list 的分页返回。
export interface ForbiddenLogListResponse {
  items: ForbiddenLogRow[];
  total: number;
  page: number;
  page_size: number;
}

// 详情里的一张图：采集失败时只有 ok。
export interface LogPicture {
  ok: boolean;
  src?: string;
}

// 违禁日志详情：比列表行多原文、JSON 段和图片。
export interface ForbiddenLogDetail extends ForbiddenLogRow {
  text: string;
  json: unknown;
  pictures: LogPicture[];
}

// 四个名单接口统一回报：一句文案加最新四态。
export interface RosterResponse extends RosterFlags {
  message: string;
}

// 回补群昵称失败的群：群号和原因。
export interface BackfillGroupFailure {
  group_id: string;
  reason: string;
}

// forbidden-log/backfill-nicknames 的返回。
export interface BackfillResponse {
  message: string;
  updated: number;
  failed: BackfillGroupFailure[];
}

// 违禁词测试回报：状态、触发词和说明。
export interface ForbiddenTestResult {
  status: string;
  trigger: string;
  message: string;
  reason: string;
}

// 图片检测测试的二维码诊断：引擎总状态、三个分层状态、命中层、是否检出、检出数量和截断载荷。预检没过时后端给空对象。
export interface ImageQrDiagnosis {
  engine?: string;
  wechat?: string;
  zxing?: string;
  qreader?: string;
  layer?: string;
  found?: boolean;
  box_count?: number;
  payloads?: string[];
  error?: string;
}

// 图片检测测试的 OCR 诊断：引擎状态、识别文字和错误。预检没过时后端给空对象。
export interface ImageOcrDiagnosis {
  engine?: string;
  text?: string;
  error?: string;
}

// forbidden/image-test 的返回：二维码、OCR、触发词、送模型与否和模型结论。gif 时多一个 note。
export interface ImageTestResult {
  qr: ImageQrDiagnosis;
  ocr: ImageOcrDiagnosis;
  trigger: string;
  plan_status: string;
  llm_called: boolean;
  verdict: string;
  reason: string;
  message: string;
  note?: string;
}

// 六个功能名单的配置键，和后端 constants 的 SETTING_LIST_KEYS 一致。
export type FeatureKey =
  | "keyword_groups"
  | "forbidden_groups"
  | "welcome_groups"
  | "verify_groups"
  | "invite_groups"
  | "forbidden_block_group_card_groups";

// 六个功能各自的开关，配置页一行里的勾选状态。
export type FeatureFlags = Record<FeatureKey, boolean>;

// 六个功能各自的群号名单。
export type FeatureLists = Record<FeatureKey, string[]>;

// settings/get 返回的整份配置：名单、文本、秒数、开关。
export interface SettingsPayload extends FeatureLists {
  welcome_text: string;
  forbidden_guideline: string;
  forbidden_samples: string;
  forbidden_remind_text: string;
  forbidden_feishu_webhook: string;
  forbidden_mute_seconds: number;
  verify_mute_seconds: number;
  forbidden_trigger_url: boolean;
  forbidden_trigger_group: boolean;
  forbidden_trigger_qq: boolean;
  forbidden_trigger_phone: boolean;
  forbidden_trigger_wechat: boolean;
}
