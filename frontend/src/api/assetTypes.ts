export interface AssetOption {id:string|number;name?:string;username?:string;parent?:string|null;color?:string}
export interface AssetOptions extends Record<string,AssetOption[]> {
 'business-groups':AssetOption[];departments:AssetOption[];users:AssetOption[];tags:AssetOption[]
}
export interface BusinessAssetSummary {
 id:string;name:string;code:string;group_name:string;department_name:string;owner_name:string
 tag_names:string;monitor_count:number;is_enabled:boolean;is_archived:boolean;sla_target:string
}
