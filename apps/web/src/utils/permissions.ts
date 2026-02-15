export type Permission =
  | 'view_dashboard'
  | 'view_schedule'
  | 'edit_schedule'
  | 'view_orders'
  | 'edit_orders'
  | 'view_inventory'
  | 'edit_inventory'
  | 'view_service'
  | 'edit_service'
  | 'view_training'
  | 'edit_training'
  | 'view_decision'
  | 'edit_decision'
  | 'view_reservation'
  | 'edit_reservation'
  | 'manage_users'
  | 'manage_roles';

export type Role = 'admin' | 'manager' | 'staff';

export const rolePermissions: Record<Role, Permission[]> = {
  admin: [
    'view_dashboard',
    'view_schedule',
    'edit_schedule',
    'view_orders',
    'edit_orders',
    'view_inventory',
    'edit_inventory',
    'view_service',
    'edit_service',
    'view_training',
    'edit_training',
    'view_decision',
    'edit_decision',
    'view_reservation',
    'edit_reservation',
    'manage_users',
    'manage_roles',
  ],
  manager: [
    'view_dashboard',
    'view_schedule',
    'edit_schedule',
    'view_orders',
    'edit_orders',
    'view_inventory',
    'edit_inventory',
    'view_service',
    'edit_service',
    'view_training',
    'edit_training',
    'view_reservation',
    'edit_reservation',
  ],
  staff: [
    'view_dashboard',
    'view_schedule',
    'view_orders',
    'view_inventory',
    'view_service',
    'view_reservation',
  ],
};

export const hasPermission = (role: Role, permission: Permission): boolean => {
  return rolePermissions[role]?.includes(permission) || false;
};

export const hasAnyPermission = (role: Role, permissions: Permission[]): boolean => {
  return permissions.some(permission => hasPermission(role, permission));
};

export const hasAllPermissions = (role: Role, permissions: Permission[]): boolean => {
  return permissions.every(permission => hasPermission(role, permission));
};
