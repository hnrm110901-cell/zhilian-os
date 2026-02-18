// 权限类型定义 - 与后端保持一致
export type Permission =
  // Agent访问权限
  | 'agent:schedule:read'
  | 'agent:schedule:write'
  | 'agent:order:read'
  | 'agent:order:write'
  | 'agent:inventory:read'
  | 'agent:inventory:write'
  | 'agent:service:read'
  | 'agent:service:write'
  | 'agent:training:read'
  | 'agent:training:write'
  | 'agent:decision:read'
  | 'agent:decision:write'
  | 'agent:reservation:read'
  | 'agent:reservation:write'
  // 用户管理权限
  | 'user:read'
  | 'user:write'
  | 'user:delete'
  // 门店管理权限
  | 'store:read'
  | 'store:write'
  | 'store:delete'
  // 系统配置权限
  | 'system:config'
  | 'system:logs';

// 角色类型定义 - 与后端保持一致
export type Role =
  | 'admin'
  | 'store_manager'
  | 'assistant_manager'
  | 'floor_manager'
  | 'customer_manager'
  | 'team_leader'
  | 'waiter'
  | 'head_chef'
  | 'station_manager'
  | 'chef'
  | 'warehouse_manager'
  | 'finance'
  | 'procurement';

/**
 * 检查权限列表中是否包含指定权限
 * 注意：前端权限检查基于从后端获取的权限列表
 */
export const hasPermission = (permissions: string[], permission: Permission): boolean => {
  return permissions.includes(permission);
};

/**
 * 检查是否拥有任意一个指定权限
 */
export const hasAnyPermission = (permissions: string[], requiredPermissions: Permission[]): boolean => {
  return requiredPermissions.some(perm => permissions.includes(perm));
};

/**
 * 检查是否拥有所有指定权限
 */
export const hasAllPermissions = (permissions: string[], requiredPermissions: Permission[]): boolean => {
  return requiredPermissions.every(perm => permissions.includes(perm));
};
