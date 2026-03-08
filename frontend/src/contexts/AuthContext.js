import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const AuthContext = createContext();

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [licenseStatus, setLicenseStatus] = useState(() => {
    const saved = localStorage.getItem('licenseStatus');
    return saved ? JSON.parse(saved) : null;
  });

  // Configure axios defaults
  axios.defaults.baseURL = '';
  axios.defaults.timeout = 10000;
  
  if (token) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }

  const login = async (credentials) => {
    try {
      const response = await axios.post('/api/auth/login', credentials, {
        timeout: 10000,
        headers: {
          'Content-Type': 'application/json',
        }
      });
      const { access_token, user: userData, license: licenseInfo } = response.data;

      setToken(access_token);
      setUser(userData);
      if (licenseInfo) {
        setLicenseStatus(licenseInfo);
        localStorage.setItem('licenseStatus', JSON.stringify(licenseInfo));
      }
      localStorage.setItem('token', access_token);
      localStorage.setItem('user', JSON.stringify(userData));
      axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
      
      return { success: true };
    } catch (error) {
      console.error('Login error:', error);
      let errorMessage = 'Login failed';
      
      if (error.code === 'ECONNREFUSED' || error.message.includes('Network Error')) {
        errorMessage = 'Cannot connect to server. Please make sure the backend is running on port 8000.';
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }
      
      return { 
        success: false, 
        error: errorMessage 
      };
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    setLicenseStatus(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('licenseStatus');
    delete axios.defaults.headers.common['Authorization'];
  };

  const checkAuth = async () => {
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const response = await axios.get('/profile');
      setUser(response.data);
    } catch (error) {
      logout();
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const value = {
    user,
    token,
    login,
    logout,
    loading,
    licenseStatus,
    setLicenseStatus,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};