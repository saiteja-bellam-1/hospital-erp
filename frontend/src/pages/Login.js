import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import FormNavContainer from '../components/FormNavContainer';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { useToast } from '../hooks/use-toast';
import axios from 'axios';
import HospitalLogo from '../components/HospitalLogo';
import {
  BedDouble,
  FlaskConical,
  Pill,
  Receipt,
  Stethoscope,
  Users,
} from 'lucide-react';

const MODULE_CHIPS = [
  { label: 'Reception', icon: Users, color: '#296DAE' },
  { label: 'Laboratory', icon: FlaskConical, color: '#00A09D' },
  { label: 'Pharmacy', icon: Pill, color: '#E4572E' },
  { label: 'Billing', icon: Receipt, color: '#F0A202' },
  { label: 'Inpatient', icon: BedDouble, color: '#3D5A80' },
  { label: 'Consultation', icon: Stethoscope, color: '#2A9D8F' },
];

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
    <div className="min-h-screen flex flex-col bg-white">
      <header className="h-16 px-6 lg:px-10 flex items-center border-b border-gray-100 bg-white flex-shrink-0">
        <HospitalLogo variant="header" />
      </header>

      <div className="flex-1 grid lg:grid-cols-2 min-h-0">
        <section className="hidden lg:flex flex-col justify-center px-12 xl:px-20 bg-white">
          <p className="text-sm font-semibold tracking-wide text-primary">
            {hospitalInfo?.name || 'KT HEALTH ERP'}
          </p>
          <h1 className="mt-4 text-5xl xl:text-[3.4rem] font-bold tracking-tight text-gray-900 leading-[1.08]">
            All your hospital,
            <br />
            on one platform.
          </h1>
          <p className="mt-5 text-lg text-gray-500 max-w-md leading-relaxed">
            Simple and efficient. Reception, lab, pharmacy, wards, and billing — open the app you need and get to work.
          </p>
          <div className="mt-10 flex flex-wrap gap-3 max-w-lg">
            {MODULE_CHIPS.map(({ label, icon: Icon, color }) => (
              <div
                key={label}
                className="flex items-center gap-2.5 rounded-xl border border-gray-100 bg-white px-3 py-2 shadow-sm"
              >
                <span
                  className="flex h-9 w-9 items-center justify-center rounded-lg text-white"
                  style={{ background: color }}
                >
                  <Icon className="h-4 w-4" />
                </span>
                <span className="text-sm font-medium text-gray-800">{label}</span>
              </div>
            ))}
          </div>
        </section>

        <section
          className="flex items-center justify-center px-4 py-12"
          style={{ background: 'hsl(30 18% 96%)' }}
        >
          <div className="w-full max-w-[420px]">
            <div className="lg:hidden flex justify-center mb-8">
              <HospitalLogo variant="login" />
            </div>
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-8 py-8">
              <h2 className="text-2xl font-bold tracking-tight text-gray-900">Sign in</h2>
              <p className="text-sm text-gray-500 mt-1 mb-6">
                Use your hospital account to continue.
              </p>
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
                  className="w-full h-11 text-sm font-semibold"
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
                  ) : 'Sign in'}
                </Button>
              </FormNavContainer>
            </div>

            {hospitalInfo && (
              <div className="text-center mt-6">
                <p className="text-xs font-medium text-gray-500">
                  {hospitalInfo.name}
                </p>
                <p className="text-[11px] mt-0.5 text-gray-400">
                  ID: <span className="font-mono">{hospitalInfo.hospital_id}</span>
                </p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default Login;
