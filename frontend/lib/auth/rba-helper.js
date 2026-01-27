import { APIClient } from '../api-client';

const fetchUserDepartment = async (getAuthHeaders, setDepartment, setUser) => {
  try {
    const apiClient = new APIClient(getAuthHeaders);
    const response = await apiClient.getUserDepartment();
    if (response?.department) {
      setDepartment(response.department);
      // Update user object with department
      setUser(prev => prev ? { ...prev, department: response.department } : null);
    }
  } catch (error) {
    console.error('Failed to fetch user department:', error);
    // Don't set error state here as it might be a temporary network issue
  }
};

export const rbaHelper = {
  fetchUserDepartment
};