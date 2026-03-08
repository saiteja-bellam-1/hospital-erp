import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Badge } from '../../../components/ui/badge';
import {
  Calendar,
  Clock,
  User,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertCircle,
  Stethoscope,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

const DoctorAvailabilityPage = () => {
  const [doctors, setDoctors] = useState([]);
  const [selectedDoctor, setSelectedDoctor] = useState('');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [availabilityData, setAvailabilityData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState('day'); // 'day' or 'week'
  const [weekData, setWeekData] = useState([]);
  const [weekStart, setWeekStart] = useState(getMonday(new Date()));

  function getMonday(d) {
    const date = new Date(d);
    const day = date.getDay();
    const diff = date.getDate() - day + (day === 0 ? -6 : 1);
    return new Date(date.setDate(diff));
  }

  useEffect(() => {
    fetchDoctors();
  }, []);

  const fetchDoctors = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/appointments/doctors', {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        const data = await response.json();
        setDoctors(data);
      }
    } catch (error) {
      console.error('Error fetching doctors:', error);
    }
  };

  const fetchDoctorAvailability = async (doctorId, date) => {
    if (!doctorId || !date) return;
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/appointments/doctors/${doctorId}/available-slots?appointment_date=${date}`,
        { headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } }
      );
      if (response.ok) {
        const data = await response.json();
        setAvailabilityData(data);
      } else {
        setAvailabilityData(null);
      }
    } catch (error) {
      console.error('Error fetching availability:', error);
      setAvailabilityData(null);
    } finally {
      setLoading(false);
    }
  };

  const fetchWeekData = async (doctorId, startDate) => {
    if (!doctorId) return;
    setLoading(true);
    const weekResults = [];
    const token = localStorage.getItem('token');

    for (let i = 0; i < 7; i++) {
      const d = new Date(startDate);
      d.setDate(d.getDate() + i);
      const dateStr = d.toISOString().split('T')[0];
      try {
        const response = await fetch(
          `/api/appointments/doctors/${doctorId}/available-slots?appointment_date=${dateStr}`,
          { headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } }
        );
        if (response.ok) {
          const data = await response.json();
          weekResults.push({
            date: dateStr,
            dayName: d.toLocaleDateString('en-US', { weekday: 'short' }),
            dayNum: d.getDate(),
            month: d.toLocaleDateString('en-US', { month: 'short' }),
            slots: data.available_slots?.length || 0,
            appointments: data.schedule_info?.existing_appointments || [],
            available: data.schedule_info?.available !== false,
            workingHours: data.schedule_info?.working_hours,
            specialSchedule: data.schedule_info?.special_schedule
          });
        } else {
          weekResults.push({ date: dateStr, dayName: d.toLocaleDateString('en-US', { weekday: 'short' }), dayNum: d.getDate(), month: d.toLocaleDateString('en-US', { month: 'short' }), slots: 0, appointments: [], available: false });
        }
      } catch {
        weekResults.push({ date: dateStr, dayName: d.toLocaleDateString('en-US', { weekday: 'short' }), dayNum: d.getDate(), month: d.toLocaleDateString('en-US', { month: 'short' }), slots: 0, appointments: [], available: false });
      }
    }
    setWeekData(weekResults);
    setLoading(false);
  };

  const handleDoctorChange = (doctorId) => {
    setSelectedDoctor(doctorId);
    setAvailabilityData(null);
    if (viewMode === 'day' && doctorId) {
      fetchDoctorAvailability(doctorId, selectedDate);
    } else if (viewMode === 'week' && doctorId) {
      fetchWeekData(doctorId, weekStart);
    }
  };

  const handleDateChange = (date) => {
    setSelectedDate(date);
    if (selectedDoctor) {
      fetchDoctorAvailability(selectedDoctor, date);
    }
  };

  const navigateWeek = (direction) => {
    const newStart = new Date(weekStart);
    newStart.setDate(newStart.getDate() + (direction * 7));
    setWeekStart(newStart);
    if (selectedDoctor) {
      fetchWeekData(selectedDoctor, newStart);
    }
  };

  const switchView = (mode) => {
    setViewMode(mode);
    if (mode === 'week' && selectedDoctor) {
      fetchWeekData(selectedDoctor, weekStart);
    } else if (mode === 'day' && selectedDoctor) {
      fetchDoctorAvailability(selectedDoctor, selectedDate);
    }
  };

  const formatTime = (timeStr) => {
    try {
      const [hours, minutes] = timeStr.split(':');
      const h = parseInt(hours);
      const ampm = h >= 12 ? 'PM' : 'AM';
      const h12 = h % 12 || 12;
      return `${h12}:${minutes} ${ampm}`;
    } catch {
      return timeStr;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'available': return 'bg-green-100 text-green-800';
      case 'busy': return 'bg-red-100 text-red-800';
      case 'break': return 'bg-yellow-100 text-yellow-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Doctor Schedule</h1>
          <p className="text-gray-600">View doctor schedules and available appointment times</p>
        </div>
        <div className="flex gap-2">
          <Button variant={viewMode === 'day' ? 'default' : 'outline'} size="sm" onClick={() => switchView('day')}>Day View</Button>
          <Button variant={viewMode === 'week' ? 'default' : 'outline'} size="sm" onClick={() => switchView('week')}>Week View</Button>
          <Button onClick={() => viewMode === 'day' ? fetchDoctorAvailability(selectedDoctor, selectedDate) : fetchWeekData(selectedDoctor, weekStart)} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Select Doctor</Label>
              <Select value={selectedDoctor} onValueChange={handleDoctorChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Choose a doctor" />
                </SelectTrigger>
                <SelectContent>
                  {doctors.map((doctor) => (
                    <SelectItem key={doctor.id} value={doctor.id.toString()}>
                      <div className="flex items-center space-x-2">
                        <Stethoscope className="h-4 w-4" />
                        <span>Dr. {doctor.first_name} {doctor.last_name}</span>
                        {doctor.specialization && <span className="text-sm text-gray-500">({doctor.specialization})</span>}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {viewMode === 'day' && (
              <div>
                <Label>Select Date</Label>
                <Input type="date" value={selectedDate} onChange={(e) => handleDateChange(e.target.value)} />
              </div>
            )}
            {viewMode === 'week' && (
              <div className="flex items-end gap-2">
                <Button variant="outline" size="sm" onClick={() => navigateWeek(-1)}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <div className="text-center flex-1">
                  <Label>Week of</Label>
                  <p className="font-medium">{weekStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - {new Date(new Date(weekStart).setDate(weekStart.getDate() + 6)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</p>
                </div>
                <Button variant="outline" size="sm" onClick={() => navigateWeek(1)}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <Card>
          <CardContent className="p-8 text-center">
            <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
            <p className="text-gray-600">Loading schedule...</p>
          </CardContent>
        </Card>
      ) : viewMode === 'week' && selectedDoctor ? (
        /* Week View */
        <div className="grid grid-cols-7 gap-2">
          {weekData.map((day) => (
            <Card key={day.date} className={`${!day.available ? 'opacity-60 bg-gray-50' : ''} ${day.date === new Date().toISOString().split('T')[0] ? 'ring-2 ring-blue-400' : ''}`}>
              <CardHeader className="p-3 pb-1">
                <div className="text-center">
                  <p className="text-xs text-gray-500">{day.dayName}</p>
                  <p className="text-lg font-bold">{day.dayNum}</p>
                  <p className="text-xs text-gray-500">{day.month}</p>
                </div>
              </CardHeader>
              <CardContent className="p-2 pt-0">
                {!day.available ? (
                  <div className="text-center py-2">
                    <XCircle className="h-4 w-4 text-red-400 mx-auto" />
                    <p className="text-xs text-gray-500 mt-1">
                      {day.specialSchedule ? day.specialSchedule.type : 'Off'}
                    </p>
                  </div>
                ) : (
                  <>
                    {day.workingHours && day.workingHours.start_time && (
                      <p className="text-xs text-center text-gray-500 mb-1">
                        {formatTime(day.workingHours.start_time)}-{formatTime(day.workingHours.end_time)}
                      </p>
                    )}
                    <div className="flex justify-between text-xs mb-2">
                      <span className="text-green-600">{day.slots} free</span>
                      <span className="text-blue-600">{day.appointments.length} booked</span>
                    </div>
                    {day.appointments.length > 0 && (
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {day.appointments.map((apt, i) => (
                          <div key={i} className="bg-blue-50 rounded p-1 text-xs">
                            <p className="font-medium">{formatTime(apt.time)}</p>
                            <p className="text-gray-600 truncate">{apt.patient_name}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : viewMode === 'day' && availabilityData ? (
        /* Day View - Same as before */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Schedule Summary */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <User className="h-5 w-5" />
                <span>Schedule Summary</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm text-gray-600">Doctor</p>
                <p className="font-semibold">{availabilityData.doctor_name}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Date</p>
                <p className="font-semibold">{new Date(selectedDate).toLocaleDateString()}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Status</p>
                <Badge className={getStatusColor(availabilityData.schedule_info?.status || 'available')}>
                  {availabilityData.schedule_info?.status || 'Available'}
                </Badge>
              </div>
              {availabilityData.schedule_info?.working_hours && availabilityData.schedule_info.working_hours.start_time && (
                <div>
                  <p className="text-sm text-gray-600">Working Hours</p>
                  <p className="font-semibold">
                    {formatTime(availabilityData.schedule_info.working_hours.start_time)} - {formatTime(availabilityData.schedule_info.working_hours.end_time)}
                  </p>
                </div>
              )}
              <div>
                <p className="text-sm text-gray-600">Available Slots</p>
                <p className="font-semibold text-green-600">{availabilityData.available_slots?.length || 0} slots</p>
              </div>
            </CardContent>
          </Card>

          {/* Available Time Slots */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Clock className="h-5 w-5" />
                <span>Available Time Slots</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {availabilityData.available_slots && availabilityData.available_slots.length > 0 ? (
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {availabilityData.available_slots.map((slot, index) => (
                    <div key={index} className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
                      <div className="flex items-center space-x-2">
                        <CheckCircle className="h-4 w-4 text-green-600" />
                        <span className="font-medium">{formatTime(slot.start_time)}</span>
                        <span className="text-gray-500">-</span>
                        <span className="font-medium">{formatTime(slot.end_time)}</span>
                      </div>
                      <span className="text-xs text-gray-600">{slot.duration} min</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <XCircle className="h-12 w-12 text-red-400 mx-auto mb-3" />
                  <p className="text-gray-500">No available slots for this date</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Existing Appointments */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Calendar className="h-5 w-5" />
                <span>Existing Appointments</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {availabilityData.schedule_info?.existing_appointments && availabilityData.schedule_info.existing_appointments.length > 0 ? (
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {availabilityData.schedule_info.existing_appointments.map((apt, index) => (
                    <div key={index} className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{formatTime(apt.time)}</span>
                        <Badge variant="secondary">{apt.status}</Badge>
                      </div>
                      <p className="text-sm text-gray-600">{apt.patient_name}</p>
                      <p className="text-xs text-gray-500">{apt.type} - {apt.duration} min</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500">No appointments scheduled</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      ) : selectedDoctor ? (
        <Card>
          <CardContent className="p-8 text-center">
            <AlertCircle className="h-12 w-12 text-yellow-500 mx-auto mb-4" />
            <p className="text-gray-600">Please select a date to view availability</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-8 text-center">
            <Stethoscope className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600">Please select a doctor to view schedule</p>
          </CardContent>
        </Card>
      )}

      {/* Special Schedule Info */}
      {viewMode === 'day' && availabilityData?.schedule_info?.special_schedule && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <AlertCircle className="h-5 w-5" />
              <span>Special Schedule</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-gray-600">Type</p>
                <p className="font-semibold capitalize">{availabilityData.schedule_info.special_schedule.type}</p>
              </div>
              {availabilityData.schedule_info.special_schedule.start_time && (
                <div>
                  <p className="text-sm text-gray-600">Modified Hours</p>
                  <p className="font-semibold">
                    {formatTime(availabilityData.schedule_info.special_schedule.start_time)} - {formatTime(availabilityData.schedule_info.special_schedule.end_time)}
                  </p>
                </div>
              )}
              {availabilityData.schedule_info.special_schedule.notes && (
                <div>
                  <p className="text-sm text-gray-600">Notes</p>
                  <p className="font-semibold">{availabilityData.schedule_info.special_schedule.notes}</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Break Times */}
      {viewMode === 'day' && availabilityData?.schedule_info?.break_times && availabilityData.schedule_info.break_times.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Clock className="h-5 w-5" />
              <span>Break Times</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {availabilityData.schedule_info.break_times.map((breakTime, index) => (
                <div key={index} className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                  <p className="font-medium">
                    {formatTime(breakTime.start_time)} - {formatTime(breakTime.end_time)}
                  </p>
                  {breakTime.description && <p className="text-sm text-gray-600">{breakTime.description}</p>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default DoctorAvailabilityPage;
