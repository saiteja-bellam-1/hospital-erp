import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardHeader, CardContent, CardFooter } from '../components/ui/card';
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
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center space-y-4">
          <div className="flex justify-center">
            <img 
              src={hospitalLogo} 
              alt="KT Health Soft - Hospital Management System" 
              className="h-32 w-auto max-w-sm"
            />
          </div>
          <p className="text-lg text-muted-foreground">Sign In to Your Account</p>
        </CardHeader>
        
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                type="text"
                autoComplete="username"
                autoFocus
                {...register('username', { 
                  required: 'Username is required' 
                })}
                className={errors.username ? 'border-destructive' : ''}
              />
              {errors.username && (
                <p className="text-sm text-destructive">{errors.username.message}</p>
              )}
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                {...register('password', { 
                  required: 'Password is required' 
                })}
                className={errors.password ? 'border-destructive' : ''}
              />
              {errors.password && (
                <p className="text-sm text-destructive">{errors.password.message}</p>
              )}
            </div>
            
            <Button 
              type="submit" 
              className="w-full"
              disabled={loading}
            >
              {loading ? 'Signing In...' : 'Sign In'}
            </Button>
          </form>
        </CardContent>
        {hospitalInfo && (
          <CardFooter className="justify-center border-t pt-4">
            <p className="text-xs text-muted-foreground">
              Hospital ID: <span className="font-mono font-medium text-gray-700">{hospitalInfo.hospital_id}</span>
              <span className="mx-2">|</span>
              {hospitalInfo.name}
            </p>
          </CardFooter>
        )}
      </Card>
    </div>
  );
};

export default Login;