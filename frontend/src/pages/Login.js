import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import FormNavContainer from '../components/FormNavContainer';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { useToast } from '../hooks/use-toast';
import axios from 'axios';
import hospitalLogo from '../assets/Final Logo KT (1).jpg';

const Login = () => {
  const [loading, setLoading] = useState(false);
  const [hospitalInfo, setHospitalInfo] = useState(null);
  const { login } = useAuth();
  const { toast } = useToast();

  const { register, handleSubmit, formState: { errors } } = useForm();

  useEffect(() => {
    const fetchHospitalInfo = async () => {
      try {
        const response = await axios.get('/api/license/status/public');
        if (response.data.hospital) {
          setHospitalInfo(response.data.hospital);
        }
      } catch (error) {
        console.error('Failed to fetch hospital info:', error);
      }
    };
    fetchHospitalInfo();
  }, []);

  const onSubmit = async (data) => {
    setLoading(true);
    const result = await login(data);
    if (!result.success) {
      toast({
        variant: "destructive",
        title: "Login Failed",
        description: result.error,
      });
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden"
      style={{
        background: 'linear-gradient(135deg, hsl(218 40% 13%) 0%, hsl(218 35% 18%) 40%, hsl(209 45% 22%) 100%)',
      }}
    >
      {/* Subtle background pattern */}
      <div className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
          backgroundSize: '32px 32px',
        }}
      />

      {/* Soft glow behind card */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full opacity-10"
        style={{
          background: 'radial-gradient(circle, hsl(209 62% 42%) 0%, transparent 70%)',
        }}
      />

      <div className="w-full max-w-[420px] relative z-10">
        {/* Login card */}
        <div className="bg-white rounded-2xl shadow-2xl shadow-black/20 overflow-hidden">
          {/* Logo section */}
          <div className="pt-10 pb-6 px-8 text-center"
            style={{
              background: 'linear-gradient(180deg, hsl(220 20% 97%) 0%, white 100%)',
            }}
          >
            <div className="flex justify-center mb-4">
              <img
                src={hospitalLogo}
                alt="KT Health Soft - Hospital Management System"
                className="h-24 w-auto max-w-[280px]"
              />
            </div>
            <p className="text-sm font-medium" style={{ color: 'hsl(220 10% 46%)' }}>
              Sign in to your account
            </p>
          </div>

          {/* Form section */}
          <div className="px-8 pb-8 pt-2">
            <FormNavContainer tag="form" onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              <div className="space-y-1.5">
                <Label htmlFor="username" className="text-sm font-medium text-gray-700">
                  Username
                </Label>
                <Input
                  id="username"
                  type="text"
                  autoComplete="username"
                  autoFocus
                  placeholder="Enter your username"
                  {...register('username', {
                    required: 'Username is required'
                  })}
                  className={`h-11 ${errors.username ? 'border-red-400 focus:ring-red-400' : ''}`}
                />
                {errors.username && (
                  <p className="text-xs text-red-500 mt-1">{errors.username.message}</p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-sm font-medium text-gray-700">
                  Password
                </Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  {...register('password', {
                    required: 'Password is required'
                  })}
                  className={`h-11 ${errors.password ? 'border-red-400 focus:ring-red-400' : ''}`}
                />
                {errors.password && (
                  <p className="text-xs text-red-500 mt-1">{errors.password.message}</p>
                )}
              </div>

              <Button
                type="submit"
                className="w-full h-11 text-sm font-semibold tracking-wide"
                style={{
                  background: 'hsl(209 62% 42%)',
                }}
                disabled={loading}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Signing in...
                  </span>
                ) : 'Sign In'}
              </Button>
            </FormNavContainer>
          </div>
        </div>

        {/* Hospital info footer */}
        {hospitalInfo && (
          <div className="text-center mt-6">
            <p className="text-xs font-medium" style={{ color: 'hsl(220 15% 55%)' }}>
              {hospitalInfo.name}
            </p>
            <p className="text-[11px] mt-0.5" style={{ color: 'hsl(220 10% 40%)' }}>
              ID: <span className="font-mono">{hospitalInfo.hospital_id}</span>
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default Login;
