import { useAuth } from '../contexts/AuthContext';
import { hasPermission, hasAnyPermission, hasAllPermissions } from '../utils/permissions';
import type { Permission } from '../utils/permissions';

export const usePermission = () => {
  const { user, permissions } = useAuth();

  const checkPermission = (permission: Permission): boolean => {
    if (!user) return false;
    return hasPermission(permissions, permission);
  };

  const checkAnyPermission = (requiredPermissions: Permission[]): boolean => {
    if (!user) return false;
    return hasAnyPermission(permissions, requiredPermissions);
  };

  const checkAllPermissions = (requiredPermissions: Permission[]): boolean => {
    if (!user) return false;
    return hasAllPermissions(permissions, requiredPermissions);
  };

  return {
    checkPermission,
    checkAnyPermission,
    checkAllPermissions,
    isAdmin: user?.role === 'admin',
    isStoreManager: user?.role === 'store_manager',
    isManager: user?.role === 'store_manager' || user?.role === 'assistant_manager' || user?.role === 'floor_manager',
  };
};
