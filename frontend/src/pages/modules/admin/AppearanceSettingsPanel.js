import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { useToast } from '../../../hooks/use-toast';
import { useLayoutPreferences } from '../../../contexts/LayoutPreferencesContext';
import LabelSettingsFields from '../../../components/LabelSettingsFields';
import { PanelLeft, PanelTop, Save, Tag } from 'lucide-react';

const DEFAULT_LAB_LABELS = {
  width_mm: 50, height_mm: 30, labels_per_row: 1, labels_per_column: 1,
  margin_top_mm: 2, margin_left_mm: 2, gutter_mm: 2, sheet_mode: 'thermal',
  sheet_width_mm: 210, sheet_height_mm: 297, show_lab_name: true, lab_name_override: null,
};

const DEFAULT_PHARMACY_LABELS = {
  width_mm: 38, height_mm: 25, labels_per_row: 1, labels_per_column: 1,
  margin_top_mm: 2, margin_left_mm: 2, gutter_mm: 2, sheet_mode: 'thermal',
  sheet_width_mm: 210, sheet_height_mm: 297, show_lab_name: false, lab_name_override: null,
};

function mergeLabelSettings(defaults, raw) {
  if (!raw) return { ...defaults };
  return { ...defaults, ...raw };
}

export default function AppearanceSettingsPanel() {
  const { toast } = useToast();
  const { navLayout, setNavLayout } = useLayoutPreferences();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('navigation');
  const [appearanceLayout, setAppearanceLayout] = useState('sidebar');
  const [labLabelSettings, setLabLabelSettings] = useState(DEFAULT_LAB_LABELS);
  const [pharmacyLabelSettings, setPharmacyLabelSettings] = useState(DEFAULT_PHARMACY_LABELS);

  useEffect(() => {
    setAppearanceLayout(navLayout === 'header' ? 'header' : 'sidebar');
  }, [navLayout]);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get('/api/hospital/print-settings');
        if (res.data.lab_label_settings) {
          setLabLabelSettings(mergeLabelSettings(DEFAULT_LAB_LABELS, res.data.lab_label_settings));
        }
        if (res.data.pharmacy_label_settings) {
          setPharmacyLabelSettings(mergeLabelSettings(DEFAULT_PHARMACY_LABELS, res.data.pharmacy_label_settings));
        }
      } catch {
        toast({
          variant: 'destructive',
          title: 'Error',
          description: 'Failed to load label settings',
        });
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [toast]);

  const handleSave = async () => {
    setSaving(true);
    try {
      if (activeTab === 'navigation') {
        const res = await axios.put('/api/hospital/ui-settings', {
          nav_layout: appearanceLayout,
        });
        const layout = res.data?.nav_layout === 'header' ? 'header' : 'sidebar';
        setNavLayout(layout);
        setAppearanceLayout(layout);
        toast({
          title: 'Navigation updated',
          description: 'Layout applies to all users on this hospital.',
        });
      } else {
        await axios.put('/api/hospital/print-settings', {
          lab_label_settings: labLabelSettings,
          pharmacy_label_settings: pharmacyLabelSettings,
        });
        toast({
          title: 'Label settings saved',
          description: 'Lab and pharmacy label dimensions updated.',
        });
      }
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: error?.response?.data?.detail || 'Failed to save appearance settings',
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading appearance settings…</p>;
  }

  return (
    <div className="space-y-4">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="navigation" className="gap-1.5">
            <PanelTop className="h-4 w-4" /> Navigation
          </TabsTrigger>
          <TabsTrigger value="labels" className="gap-1.5">
            <Tag className="h-4 w-4" /> Label printing
          </TabsTrigger>
        </TabsList>

        <TabsContent value="navigation" className="mt-4 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center text-lg">
                <PanelTop className="h-5 w-5 mr-2" />
                Navigation layout
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Applies to all users on this hospital. Changes take effect immediately after save.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl">
                <button
                  type="button"
                  onClick={() => setAppearanceLayout('sidebar')}
                  className={`flex items-start gap-3 rounded-lg border-2 p-4 text-left transition-colors ${
                    appearanceLayout === 'sidebar'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-muted-foreground/30'
                  }`}
                >
                  <PanelLeft className="h-5 w-5 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-medium">Side menu</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      Classic left sidebar with collapsible sections.
                    </p>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => setAppearanceLayout('header')}
                  className={`flex items-start gap-3 rounded-lg border-2 p-4 text-left transition-colors ${
                    appearanceLayout === 'header'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-muted-foreground/30'
                  }`}
                >
                  <PanelTop className="h-5 w-5 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-medium">Top menu</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      Horizontal header nav with full-width pages and search.
                    </p>
                  </div>
                </button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="labels" className="mt-4 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Thermal &amp; Avery labels</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Configure dimensions for lab sample tube labels and pharmacy batch stickers.
                Thermal mode prints one label per page; Avery mode lays out a grid on a sheet.
              </p>
              <LabelSettingsFields
                title="Lab sample labels"
                settings={labLabelSettings}
                onChange={setLabLabelSettings}
                showLabName
              />
              <LabelSettingsFields
                title="Pharmacy batch labels"
                settings={pharmacyLabelSettings}
                onChange={setPharmacyLabelSettings}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="flex items-center gap-3">
        <Button type="button" onClick={handleSave} disabled={saving}>
          <Save className="h-4 w-4 mr-2" />
          {saving ? 'Saving…' : activeTab === 'navigation' ? 'Save navigation' : 'Save label settings'}
        </Button>
        {activeTab === 'navigation' && appearanceLayout === navLayout && (
          <span className="text-xs text-muted-foreground">No navigation changes to save.</span>
        )}
      </div>
    </div>
  );
}
