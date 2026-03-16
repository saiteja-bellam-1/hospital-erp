import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { useToast } from '../../hooks/use-toast';
import axios from 'axios';
import {
  FolderSync, FolderOpen, Plus, X, Play, CheckCircle2, AlertCircle, Loader2
} from 'lucide-react';

const BackupManagement = () => {
  const [locations, setLocations] = useState([]);
  const [newPath, setNewPath] = useState('');
  const [loading, setLoading] = useState(true);
  const [backing, setBacking] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [backupResult, setBackupResult] = useState(null);
  const { toast } = useToast();

  const browseFolder = async () => {
    setBrowsing(true);
    try {
      const res = await fetch('/api/setup/browse-folder');
      const data = await res.json();
      if (data.path) {
        setNewPath(data.path);
      }
    } catch {
      toast({ variant: 'destructive', title: 'Browse unavailable', description: 'Could not open folder picker' });
    } finally {
      setBrowsing(false);
    }
  };

  useEffect(() => {
    fetchLocations();
  }, []);

  const fetchLocations = async () => {
    try {
      const res = await axios.get('/api/backup/locations');
      setLocations(res.data.locations || []);
    } catch (error) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load backup locations' });
    } finally {
      setLoading(false);
    }
  };

  const saveLocations = async (newLocations) => {
    try {
      const res = await axios.put('/api/backup/locations', { locations: newLocations });
      setLocations(res.data.locations || []);
      if (res.data.errors?.length > 0) {
        toast({
          variant: 'destructive',
          title: 'Some paths invalid',
          description: res.data.errors.map(e => `${e.path}: ${e.error}`).join('; '),
        });
      } else {
        toast({ title: 'Saved', description: 'Backup locations updated' });
      }
    } catch (error) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to save locations' });
    }
  };

  const addLocation = () => {
    const path = newPath.trim();
    if (path && !locations.includes(path)) {
      const updated = [...locations, path];
      saveLocations(updated);
      setNewPath('');
    }
  };

  const removeLocation = (index) => {
    const updated = locations.filter((_, i) => i !== index);
    saveLocations(updated);
  };

  const runBackup = async () => {
    setBacking(true);
    setBackupResult(null);
    try {
      const res = await axios.post('/api/backup/run');
      setBackupResult(res.data);
      const allOk = res.data.results?.every(r => r.success);
      toast({
        title: allOk ? 'Backup Complete' : 'Backup Partial',
        description: allOk
          ? `Database backed up to ${res.data.results.length} location(s)`
          : 'Some backup locations failed. Check results below.',
        variant: allOk ? 'default' : 'destructive',
      });
    } catch (error) {
      const msg = error.response?.data?.detail || 'Backup failed';
      toast({ variant: 'destructive', title: 'Backup Failed', description: msg });
    } finally {
      setBacking(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">Database Backup</h1>
        <p className="text-muted-foreground">
          Configure backup locations and run manual backups of your database.
        </p>
      </div>

      {/* Backup Locations */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderSync className="w-5 h-5" />
            Backup Locations
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              placeholder="E:\Backups\KTHEALTHERP or network path"
              onKeyDown={(e) => e.key === 'Enter' && addLocation()}
            />
            <Button variant="outline" onClick={browseFolder} disabled={browsing}>
              <FolderOpen className="w-4 h-4 mr-1" />
              {browsing ? 'Opening...' : 'Browse'}
            </Button>
            <Button onClick={addLocation} disabled={!newPath.trim()}>
              <Plus className="w-4 h-4 mr-1" /> Add
            </Button>
          </div>

          {locations.length > 0 ? (
            <div className="space-y-2">
              {locations.map((loc, i) => (
                <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-4 py-3 border">
                  <code className="text-sm">{loc}</code>
                  <button
                    onClick={() => removeLocation(i)}
                    className="text-gray-400 hover:text-red-500 ml-2"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              No backup locations configured. Add a folder path above.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Run Backup */}
      <Card>
        <CardHeader>
          <CardTitle>Run Backup Now</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Creates a timestamped copy of the database in each backup location.
          </p>
          <Button
            onClick={runBackup}
            disabled={backing || locations.length === 0}
            size="lg"
          >
            {backing ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Backing up...</>
            ) : (
              <><Play className="w-4 h-4 mr-2" /> Run Backup Now</>
            )}
          </Button>

          {backupResult && (
            <div className="space-y-2 mt-4">
              <p className="text-sm font-medium">
                Backup file: <code className="bg-gray-100 px-1 rounded">{backupResult.backup_file}</code>
              </p>
              {backupResult.results?.map((r, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-2 text-sm p-2 rounded ${
                    r.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                  }`}
                >
                  {r.success ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                  <span>{r.message}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default BackupManagement;
