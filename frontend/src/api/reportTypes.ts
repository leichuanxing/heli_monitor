export interface ReportScopeOptions {
  businesses: {id:string;name:string}[]
  monitors: {id:string;name:string;business_id:string;is_enabled:boolean}[]
}
export interface SlaRecord {
  monitor_id:string;monitor_name:string;business_name:string;availability:number|null
  samples:number;excluded_samples:number;average_latency_ms:number|null;sla_target:string|number;target_met:boolean|null
}
export interface SlaReport {
  period_days?:number;start_at?:string;end_at?:string;generated_at?:string;formula?:string;data_note?:string
  summary:{monitors?:number;availability?:number|null;targets_met?:number;included_samples?:number;excluded_samples?:number}
  results:SlaRecord[]
}
