import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Calendar, Clock, Activity, Plus, Save, AlertCircle, CheckCircle2 } from 'lucide-react';

const AvailabilityModule = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  
  // Availability management state
  const [availabilitySettings, setAvailabilitySettings] = useState(null);
  const [specialSchedules, setSpecialSchedules] = useState([]);
  const [showSpecialScheduleDialog, setShowSpecialScheduleDialog] = useState(false);
  const [availabilityStatus, setAvailabilityStatus] = useState('available');
  const [statusMessage, setStatusMessage] = useState('');
  
  const [specialScheduleForm, setSpecialScheduleForm] = useState({
    date: '',
    schedule_type: 'holiday',
    start_time: '',
    end_time: '',
    title: '',
    description: '',
    emergency_only: false,
    notify_patients: true
  });

  useEffect(() => {
    fetchUserProfile();
  }, []);

  const fetchUserProfile = async () => {
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const userData = JSON.parse(userStr);
        setUser(userData);
        
        if (userData.role === 'doctor') {
          fetchAvailabilitySettings();
          fetchSpecialSchedules();
        }
      }
    } catch (error) {
      console.error('Error fetching user profile:', error);
    }
  };

  // Availability Management Functions
  const fetchAvailabilitySettings = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/doctor-availability/settings', {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setAvailabilitySettings(data);
      }
    } catch (error) {
      console.error('Error fetching availability settings:', error);
    }
  };

  const updateAvailabilitySettings = async (settings) => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      const response = await fetch('/api/doctor-availability/settings', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(settings)
      });
      
      if (response.ok) {
        const data = await response.json();
        setAvailabilitySettings(data);
        alert('Settings updated successfully!');
        return true;
      } else {
        const error = await response.json();
        alert(`Error updating settings: ${error.detail || 'Unknown error'}`);
        return false;
      }
    } catch (error) {
      console.error('Error updating availability settings:', error);
      alert('Error updating settings. Please try again.');
      return false;
    } finally {
      setLoading(false);
    }
  };

  const fetchSpecialSchedules = async () => {
    try {
      const token = localStorage.getItem('token');
      const today = new Date().toISOString().split('T')[0];
      const futureDate = new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      
      const response = await fetch(`/api/doctor-availability/special-schedule?start_date=${today}&end_date=${futureDate}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSpecialSchedules(data);
      }
    } catch (error) {
      console.error('Error fetching special schedules:', error);
    }
  };

  const createSpecialSchedule = async () => {
    try {
      setLoading(true);
      
      // Validate required fields
      if (!specialScheduleForm.date || !specialScheduleForm.title) {
        alert('Please fill in all required fields (Date and Title)');
        return false;
      }

      // Validate modified hours require start and end times
      if (specialScheduleForm.schedule_type === 'modified_hours' && 
          (!specialScheduleForm.start_time || !specialScheduleForm.end_time)) {
        alert('Modified hours require both start and end times');
        return false;
      }

      const token = localStorage.getItem('token');
      
      // Prepare the data for submission
      const submissionData = {
        date: specialScheduleForm.date,
        schedule_type: specialScheduleForm.schedule_type,
        title: specialScheduleForm.title,
        description: specialScheduleForm.description || null,
        emergency_only: specialScheduleForm.emergency_only,
        notify_patients: specialScheduleForm.notify_patients
      };

      // Only include time fields for modified_hours
      if (specialScheduleForm.schedule_type === 'modified_hours') {
        submissionData.start_time = specialScheduleForm.start_time;
        submissionData.end_time = specialScheduleForm.end_time;
      }

      const response = await fetch('/api/doctor-availability/special-schedule', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(submissionData)
      });
      
      if (response.ok) {
        await fetchSpecialSchedules();
        setShowSpecialScheduleDialog(false);
        setSpecialScheduleForm({
          date: '',
          schedule_type: 'holiday',
          start_time: '',
          end_time: '',
          title: '',
          description: '',
          emergency_only: false,
          notify_patients: true
        });
        alert('Special schedule created successfully!');
        return true;
      } else {
        const errorData = await response.json();
        let errorMessage = 'Unknown error';
        
        if (response.status === 422) {
          // Validation errors
          if (errorData.detail && Array.isArray(errorData.detail)) {
            errorMessage = errorData.detail.map(err => err.msg).join(', ');
          } else if (errorData.detail) {
            errorMessage = errorData.detail;
          } else {
            errorMessage = 'Validation error - please check your input';
          }
        } else if (errorData.detail) {
          errorMessage = errorData.detail;
        }
        
        alert(`Error creating special schedule: ${errorMessage}`);
        console.error('API Error:', errorData);
        return false;
      }
    } catch (error) {
      console.error('Error creating special schedule:', error);
      alert('Network error. Please check your connection and try again.');
      return false;
    } finally {
      setLoading(false);
    }
  };

  const updateAvailabilityStatus = async (newStatus, message = '') => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/doctor-availability/status', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          status: newStatus,
          status_message: message
        })
      });
      
      if (response.ok) {
        setAvailabilityStatus(newStatus);
        setStatusMessage(message);
        alert('Status updated successfully!');
        return true;
      } else {
        const error = await response.json();
        alert(`Error updating status: ${error.detail || 'Unknown error'}`);
        return false;
      }
    } catch (error) {
      console.error('Error updating availability status:', error);
      alert('Error updating status. Please try again.');
      return false;
    }
  };

  if (!user || user.role !== 'doctor') {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Card className="w-96">
          <CardContent className="flex flex-col items-center p-6">
            <AlertCircle className="h-12 w-12 text-amber-500 mb-4" />
            <h3 className="text-lg font-semibold mb-2">Access Restricted</h3>
            <p className="text-gray-600 text-center">
              Availability management is only available for doctors.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Availability Management</h1>
          <p className="text-gray-600">
            Manage your schedule, working hours, and availability status
          </p>
        </div>
        <Card className="p-4">
          <div className="text-center">
            <div className={`text-2xl font-bold ${
              availabilityStatus === 'available' ? 'text-green-600' :
              availabilityStatus === 'busy' ? 'text-yellow-600' :
              availabilityStatus === 'in_consultation' ? 'text-blue-600' :
              availabilityStatus === 'on_break' ? 'text-orange-600' :
              'text-red-600'
            }`}>
              {availabilityStatus.replace('_', ' ').toUpperCase()}
            </div>
            <div className="text-sm text-gray-600">Current Status</div>
          </div>
        </Card>
      </div>

      {/* Current Status Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Current Availability Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className={`h-3 w-3 rounded-full ${
                availabilityStatus === 'available' ? 'bg-green-500' :
                availabilityStatus === 'busy' ? 'bg-yellow-500' :
                availabilityStatus === 'in_consultation' ? 'bg-blue-500' :
                availabilityStatus === 'on_break' ? 'bg-orange-500' :
                'bg-red-500'
              }`}></div>
              <span className="font-medium capitalize">{availabilityStatus.replace('_', ' ')}</span>
            </div>
            <Select value={availabilityStatus} onValueChange={(value) => updateAvailabilityStatus(value, statusMessage)}>
              <SelectTrigger className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="available">Available</SelectItem>
                <SelectItem value="busy">Busy</SelectItem>
                <SelectItem value="in_consultation">In Consultation</SelectItem>
                <SelectItem value="on_break">On Break</SelectItem>
                <SelectItem value="unavailable">Unavailable</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Input
              placeholder="Optional status message for receptionists..."
              value={statusMessage}
              onChange={(e) => setStatusMessage(e.target.value)}
              className="flex-1"
            />
            <Button
              onClick={() => updateAvailabilityStatus(availabilityStatus, statusMessage)}
              size="sm"
            >
              Update
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Weekly Schedule Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Weekly Schedule Settings
          </CardTitle>
        </CardHeader>
        <CardContent>
          {availabilitySettings ? (
            <div className="space-y-6">
              {/* Quick Settings Row */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 bg-gray-50 rounded-lg">
                <div>
                  <Label className="text-sm font-medium">Consultation Duration</Label>
                  <Select
                    value={availabilitySettings.default_consultation_duration.toString()}
                    onValueChange={(value) => setAvailabilitySettings({
                      ...availabilitySettings,
                      default_consultation_duration: parseInt(value)
                    })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="15">15 minutes</SelectItem>
                      <SelectItem value="20">20 minutes</SelectItem>
                      <SelectItem value="30">30 minutes</SelectItem>
                      <SelectItem value="45">45 minutes</SelectItem>
                      <SelectItem value="60">1 hour</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-sm font-medium">Break Between Appointments</Label>
                  <Select
                    value={availabilitySettings.buffer_minutes.toString()}
                    onValueChange={(value) => setAvailabilitySettings({
                      ...availabilitySettings,
                      buffer_minutes: parseInt(value)
                    })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">No break</SelectItem>
                      <SelectItem value="5">5 minutes</SelectItem>
                      <SelectItem value="10">10 minutes</SelectItem>
                      <SelectItem value="15">15 minutes</SelectItem>
                      <SelectItem value="20">20 minutes</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-sm font-medium">Emergency Slots</Label>
                  <Select
                    value={availabilitySettings.emergency_slot_percentage.toString()}
                    onValueChange={(value) => setAvailabilitySettings({
                      ...availabilitySettings,
                      emergency_slot_percentage: parseInt(value)
                    })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">No emergency slots</SelectItem>
                      <SelectItem value="10">10% reserve</SelectItem>
                      <SelectItem value="20">20% reserve</SelectItem>
                      <SelectItem value="30">30% reserve</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Working Days */}
              <div>
                <Label className="text-base font-medium mb-3 block">Working Days</Label>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {Object.entries(availabilitySettings.weekly_schedule).map(([day, schedule]) => (
                    <div key={day} className="border rounded-lg p-3">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="font-medium capitalize">{day}</h3>
                        <input
                          type="checkbox"
                          checked={schedule.enabled}
                          onChange={(e) => {
                            const newSchedule = {
                              ...availabilitySettings.weekly_schedule,
                              [day]: { ...schedule, enabled: e.target.checked }
                            };
                            setAvailabilitySettings({
                              ...availabilitySettings,
                              weekly_schedule: newSchedule
                            });
                          }}
                          className="w-4 h-4"
                        />
                      </div>
                      {schedule.enabled && (
                        <div className="space-y-2">
                          <div className="text-xs text-gray-600 mb-1">Working Hours</div>
                          <div className="flex gap-1 items-center">
                            <Input
                              type="time"
                              value={schedule.start_time}
                              onChange={(e) => {
                                const newSchedule = {
                                  ...availabilitySettings.weekly_schedule,
                                  [day]: { ...schedule, start_time: e.target.value }
                                };
                                setAvailabilitySettings({
                                  ...availabilitySettings,
                                  weekly_schedule: newSchedule
                                });
                              }}
                              className="text-xs"
                            />
                            <span className="text-xs text-gray-500">to</span>
                            <Input
                              type="time"
                              value={schedule.end_time}
                              onChange={(e) => {
                                const newSchedule = {
                                  ...availabilitySettings.weekly_schedule,
                                  [day]: { ...schedule, end_time: e.target.value }
                                };
                                setAvailabilitySettings({
                                  ...availabilitySettings,
                                  weekly_schedule: newSchedule
                                });
                              }}
                              className="text-xs"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end pt-4 border-t">
                <Button
                  onClick={() => updateAvailabilitySettings(availabilitySettings)}
                  disabled={loading}
                  className="flex items-center gap-2"
                >
                  <Save className="h-4 w-4" />
                  {loading ? 'Saving...' : 'Save Schedule Settings'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <Clock className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-500">Loading availability settings...</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Special Schedules (Holidays/Leaves) */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5" />
              Special Schedules & Holidays
            </CardTitle>
            <Button
              onClick={() => setShowSpecialScheduleDialog(true)}
              size="sm"
              className="flex items-center gap-2"
            >
              <Plus className="h-4 w-4" />
              Add Special Schedule
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {specialSchedules.length > 0 ? (
            <div className="space-y-2">
              {specialSchedules.map((schedule) => (
                <div key={schedule.id} className="flex items-center justify-between p-3 border rounded-lg">
                  <div className="flex-1">
                    <div className="font-medium">{schedule.title}</div>
                    <div className="text-sm text-gray-600">
                      {new Date(schedule.date).toLocaleDateString()} - {schedule.schedule_type}
                      {schedule.start_time && schedule.end_time && (
                        <span> ({schedule.start_time} - {schedule.end_time})</span>
                      )}
                    </div>
                    {schedule.description && (
                      <div className="text-sm text-gray-500 mt-1">{schedule.description}</div>
                    )}
                  </div>
                  <Badge variant={
                    schedule.schedule_type === 'holiday' ? 'destructive' :
                    schedule.schedule_type === 'leave' ? 'secondary' :
                    schedule.schedule_type === 'modified_hours' ? 'outline' : 'default'
                  }>
                    {schedule.schedule_type.replace('_', ' ')}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-500">No special schedules configured</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Special Schedule Dialog */}
      <Dialog open={showSpecialScheduleDialog} onOpenChange={setShowSpecialScheduleDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add Special Schedule</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-sm font-medium">
                Date <span className="text-red-500">*</span>
              </Label>
              <Input
                type="date"
                value={specialScheduleForm.date}
                onChange={(e) => setSpecialScheduleForm({
                  ...specialScheduleForm,
                  date: e.target.value
                })}
                className={!specialScheduleForm.date ? 'border-red-200' : ''}
              />
            </div>

            <div>
              <Label className="text-sm font-medium">Type</Label>
              <Select
                value={specialScheduleForm.schedule_type}
                onValueChange={(value) => setSpecialScheduleForm({
                  ...specialScheduleForm,
                  schedule_type: value,
                  // Clear time fields when switching away from modified_hours
                  start_time: value === 'modified_hours' ? specialScheduleForm.start_time : '',
                  end_time: value === 'modified_hours' ? specialScheduleForm.end_time : ''
                })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="holiday">Holiday - Full day off</SelectItem>
                  <SelectItem value="leave">Personal Leave - Full day off</SelectItem>
                  <SelectItem value="modified_hours">Modified Hours - Different schedule</SelectItem>
                  <SelectItem value="emergency_only">Emergency Only - Limited availability</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {specialScheduleForm.schedule_type === 'modified_hours' && (
              <div className="grid grid-cols-2 gap-2 p-3 bg-blue-50 rounded-lg">
                <div>
                  <Label className="text-sm font-medium">
                    Start Time <span className="text-red-500">*</span>
                  </Label>
                  <Input
                    type="time"
                    value={specialScheduleForm.start_time}
                    onChange={(e) => setSpecialScheduleForm({
                      ...specialScheduleForm,
                      start_time: e.target.value
                    })}
                    className={!specialScheduleForm.start_time ? 'border-red-200' : ''}
                  />
                </div>
                <div>
                  <Label className="text-sm font-medium">
                    End Time <span className="text-red-500">*</span>
                  </Label>
                  <Input
                    type="time"
                    value={specialScheduleForm.end_time}
                    onChange={(e) => setSpecialScheduleForm({
                      ...specialScheduleForm,
                      end_time: e.target.value
                    })}
                    className={!specialScheduleForm.end_time ? 'border-red-200' : ''}
                  />
                </div>
              </div>
            )}

            <div>
              <Label className="text-sm font-medium">
                Title <span className="text-red-500">*</span>
              </Label>
              <Input
                placeholder="e.g., Christmas Holiday, Medical Conference"
                value={specialScheduleForm.title}
                onChange={(e) => setSpecialScheduleForm({
                  ...specialScheduleForm,
                  title: e.target.value
                })}
                className={!specialScheduleForm.title ? 'border-red-200' : ''}
              />
            </div>

            <div>
              <Label className="text-sm font-medium">Description (Optional)</Label>
              <Textarea
                placeholder="Additional details..."
                value={specialScheduleForm.description}
                onChange={(e) => setSpecialScheduleForm({
                  ...specialScheduleForm,
                  description: e.target.value
                })}
                rows={2}
              />
            </div>

            <div className="flex items-center space-x-2 p-2 bg-gray-50 rounded">
              <input
                type="checkbox"
                id="notify-patients"
                checked={specialScheduleForm.notify_patients}
                onChange={(e) => setSpecialScheduleForm({
                  ...specialScheduleForm,
                  notify_patients: e.target.checked
                })}
                className="w-4 h-4"
              />
              <Label htmlFor="notify-patients" className="text-sm">
                Notify patients about schedule changes
              </Label>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t">
              <Button
                variant="outline"
                onClick={() => setShowSpecialScheduleDialog(false)}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button
                onClick={createSpecialSchedule}
                disabled={!specialScheduleForm.date || !specialScheduleForm.title || loading}
                className="min-w-[100px]"
              >
                {loading ? 'Creating...' : 'Create Schedule'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AvailabilityModule;