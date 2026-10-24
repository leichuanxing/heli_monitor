export interface IamRole {id:string;name:string;code:string;permissions:string[];effective_permissions:string[];is_system_role:boolean;is_enabled:boolean;user_count?:number}
export interface IamDepartment {id:string;name:string;parent_id:string|null;is_enabled:boolean}
export interface IamOptions {roles:IamRole[];departments:IamDepartment[]}
