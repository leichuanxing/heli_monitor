export interface MonitorResult {
  id:number; monitor:string; monitor_name:string; monitor_type:string; monitor_target:string; business_name:string
  checked_at:string; success:boolean; latency_ms:number|null; status_code:number|null
  packet_loss:number|null; ssl_days_remaining:number|null; error_type:string|null; error_summary:string|null
  monitor_snapshot?:Record<string,string>; metrics:Record<string,unknown>; detail:Record<string,unknown>; assertions:Array<Record<string,unknown>>
}
export interface HistorySummary {
  total:number; passed:number; failed:number; availability:number|null
  average_latency_ms:number|null; min_latency_ms:number|null; max_latency_ms:number|null
  first_checked_at:string|null; last_checked_at:string|null
}
export interface HistoryResponse {
  count:number; next:string|null; previous:string|null; results:MonitorResult[]
  summary:HistorySummary; series:Array<{id:number;monitor:string;at:string;success:boolean;latency_ms:number|null}>
  checked_after:string; checked_before:string; bucket:'raw'; retention_days:number; note:string
}
export interface BatchStart {token:string;total:number}
export interface BatchStatus {total:number;completed:number;passed:number;failed:number;skipped:number;done:boolean;results:Array<Partial<MonitorResult>&{monitor:string;name:string;state:string;message?:string}>}
