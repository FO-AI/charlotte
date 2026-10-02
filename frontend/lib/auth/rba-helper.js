import { APIClient } from '../api-client';

const fetchUserDepartment = async (getAuthHeaders, setDepartment, setUser) => {
  const applyDepartment = (department) => {
    // '' means fetched but unmapped; null is reserved for "not fetched yet".
    const value = department || '';
    setDepartment(value);
    setUser((prev) => (prev ? { ...prev, department: value } : null));
  };

  try {
    const apiClient = new APIClient(getAuthHeaders);
    const response = await apiClient.getUserDepartment();
    applyDepartment(response?.department);
  } catch (error) {
    console.error('Failed to fetch user department:', error);
    // Do not leave the auth callback spinning forever on network/API failure.
    applyDepartment('');
  }
};

export const rbaHelper = {
  fetchUserDepartment
};
