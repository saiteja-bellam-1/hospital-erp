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

  // Global 401 interceptor — auto-logout on expired/invalid token
  // Skip the interceptor for the login endpoint itself to avoid clearing a
  // non-existent session when login credentials are wrong.
  // Also handle 503 with `maintenance: true` body by surfacing a global
  // event the App-level modal can subscribe to.
  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      (response) => response,
      (error) => {
        const isLoginRequest = error.config?.url?.includes('/api/auth/login');
        if (error.response?.status === 401 && token && !isLoginRequest) {
          // Token expired or invalid — clear session
          setToken(null);
          setUser(null);
          setLicenseStatus(null);
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          localStorage.removeItem('licenseStatus');
          delete axios.defaults.headers.common['Authorization'];
        }
        if (error.response?.status === 503 && error.response?.data?.maintenance) {
          // Broadcast so a top-level modal can render and auto-dismiss.
          try {
            window.dispatchEvent(new CustomEvent('app:maintenance', {
              detail: error.response.data,
            }));
          } catch {
            // Older browsers without CustomEvent constructor — ignore.
          }
        }
        return Promise.reject(error);
      }
    );
    return () => axios.interceptors.response.eject(interceptor);
  }, [token]);

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
      
      if (error.code === 'ECONNREFUSED' || error.message?.includes('Network Error')) {
        errorMessage = 'Cannot connect to server. Please make sure the backend is running.';
      } else if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        errorMessage = 'Request timed out. The server took too long to respond. Please try again.';
      } else if (error.response?.data?.detail) {
        const detail = error.response.data.detail;
        errorMessage = typeof detail === 'string' ? detail : 'Login failed. Please try again.';
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
      localStorage.setItem('user', JSON.stringify(response.data));
    } catch (error) {
      logout();
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const clearMustChangePassword = () => {
    if (!user) return;
    const updated = { ...user, must_change_password: false };
    setUser(updated);
    localStorage.setItem('user', JSON.stringify(updated));
  };

  const value = {
    user,
    token,
    login,
    logout,
    loading,
    licenseStatus,
    setLicenseStatus,
    clearMustChangePassword,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};