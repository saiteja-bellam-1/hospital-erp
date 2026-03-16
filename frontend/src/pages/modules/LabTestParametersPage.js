import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { ConfirmDialog } from '../../components/ui/confirm-dialog';
import {
  ArrowLeft, Plus, Edit2, Trash2, GripVertical, Printer, Layers,
  FlaskConical, FolderPlus, ChevronRight, Loader2
} from 'lucide-react';
import axios from 'axios';

const LabTestParametersPage = () => {
  const { testId } = useParams();
  const navigate = useNavigate();

  const [test, setTest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Parameter dialog
  const [showParamDialog, setShowParamDialog] = useState(false);
  const [editingParam, setEditingParam] = useState(null);
  const [genderSpecific, setGenderSpecific] = useState(false);
  const [paramForm, setParamForm] = useState({
    parameter_name: '', unit: '', method: '', section: '', field_type: 'numeric',
    reference_min_male: '', reference_max_male: '',
    reference_min_female: '', reference_max_female: '',
    reference_min_default: '', reference_max_default: '',
    possible_values: '', display_order: 0
  });

  // Section rename / create
  const [renamingSection, setRenamingSection] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const renameInputRef = useRef(null);
  const [showNewSectionInput, setShowNewSectionInput] = useState(false);
  const [newSectionName, setNewSectionName] = useState('');
  const newSectionInputRef = useRef(null);

  // Collapsed sections
  const [collapsedSections, setCollapsedSections] = useState(new Set());

  // Drag state
  const [dragItem, setDragItem] = useState(null); // { paramId, fromSection }
  const [dragOverTarget, setDragOverTarget] = useState(null); // { paramId, section }

  // Confirm
  const [confirmState, setConfirmState] = useState({ open: false });
  const confirm = (message, onConfirm, title) =>
    setConfirmState({ open: true, message, onConfirm, title });

  // Feedback
  const [feedback, setFeedback] = useState({ message: '', type: '' });
  const showFeedback = (message, type = 'success') => {
    setFeedback({ message, type });
    setTimeout(() => setFeedback({ message: '', type: '' }), 3000);
  };

  // ============ Data ============

  const fetchTest = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/api/lab/tests/${testId}`);
      setTest(res.data);
    } catch (err) {
      showFeedback('Failed to load test', 'error');
    } finally {
      setLoading(false);
    }
  }, [testId]);

  useEffect(() => { fetchTest(); }, [fetchTest]);

  // ============ Helpers ============

  const getGroupedParams = () => {
    if (!test?.parameters) return { sections: [], sectionMap: {} };
    const sectionMap = {};
    const sections = [];
    test.parameters.forEach(p => {
      const sec = p.section || '';
      if (!sectionMap[sec]) {
        sectionMap[sec] = [];
        sections.push(sec);
      }
      sectionMap[sec].push(p);
    });
    return { sections, sectionMap };
  };

  const existingSections = test?.parameters
    ? [...new Set(test.parameters.map(p => p.section).filter(Boolean))]
    : [];

  // ============ Parameter CRUD ============

  const openParamDialog = (param = null, defaultSection = '') => {
    if (param) {
      setEditingParam(param);
      const hasGenderRanges = param.reference_min_male != null || param.reference_max_male != null ||
        param.reference_min_female != null || param.reference_max_female != null;
      setGenderSpecific(hasGenderRanges);
      setParamForm({
        parameter_name: param.parameter_name,
        unit: param.unit || '',
        method: param.method || '',
        section: param.section || '',
        field_type: param.field_type || 'numeric',
        reference_min_male: param.reference_min_male ?? '',
        reference_max_male: param.reference_max_male ?? '',
        reference_min_female: param.reference_min_female ?? '',
        reference_max_female: param.reference_max_female ?? '',
        reference_min_default: param.reference_min_default ?? '',
        reference_max_default: param.reference_max_default ?? '',
        possible_values: param.possible_values ? param.possible_values.join(', ') : '',
        display_order: param.display_order || 0
      });
    } else {
      setEditingParam(null);
      setGenderSpecific(false);
      setParamForm({
        parameter_name: '', unit: '', method: '', section: defaultSection, field_type: 'numeric',
        reference_min_male: '', reference_max_male: '',
        reference_min_female: '', reference_max_female: '',
        reference_min_default: '', reference_max_default: '',
        possible_values: '', display_order: 0
      });
    }
    setShowParamDialog(true);
  };

  const handleSaveParam = async () => {
    if (!paramForm.parameter_name.trim()) return;
    const payload = {
      parameter_name: paramForm.parameter_name,
      unit: paramForm.unit || null,
      method: paramForm.method || null,
      section: paramForm.section || null,
      field_type: paramForm.field_type,
      reference_min_male: genderSpecific && paramForm.reference_min_male !== '' ? parseFloat(paramForm.reference_min_male) : null,
      reference_max_male: genderSpecific && paramForm.reference_max_male !== '' ? parseFloat(paramForm.reference_max_male) : null,
      reference_min_female: genderSpecific && paramForm.reference_min_female !== '' ? parseFloat(paramForm.reference_min_female) : null,
      reference_max_female: genderSpecific && paramForm.reference_max_female !== '' ? parseFloat(paramForm.reference_max_female) : null,
      reference_min_default: paramForm.reference_min_default !== '' ? parseFloat(paramForm.reference_min_default) : null,
      reference_max_default: paramForm.reference_max_default !== '' ? parseFloat(paramForm.reference_max_default) : null,
      possible_values: paramForm.field_type === 'select' && paramForm.possible_values
        ? paramForm.possible_values.split(',').map(v => v.trim()).filter(Boolean)
        : null,
      display_order: parseInt(paramForm.display_order) || 0
    };
    setSaving(true);
    try {
      if (editingParam) {
        await axios.put(`/api/lab/tests/${testId}/parameters/${editingParam.id}`, payload);
        showFeedback('Parameter updated');
      } else {
        await axios.post(`/api/lab/tests/${testId}/parameters`, payload);
        showFeedback('Parameter added');
      }
      setShowParamDialog(false);
      fetchTest();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save parameter', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteParam = (paramId) => {
    confirm('Delete this parameter?', async () => {
      try {
        await axios.delete(`/api/lab/tests/${testId}/parameters/${paramId}`);
        showFeedback('Parameter deleted');
        fetchTest();
      } catch (err) {
        showFeedback(err.response?.data?.detail || 'Failed to delete parameter', 'error');
      }
    }, 'Delete Parameter');
  };

  // ============ Section operations ============

  // Helper to build a clean payload from a param object with an optional section override
  const buildParamPayload = (p, sectionOverride) => ({
    parameter_name: p.parameter_name,
    unit: p.unit || null,
    method: p.method || null,
    section: sectionOverride !== undefined ? sectionOverride : (p.section || null),
    field_type: p.field_type || 'numeric',
    reference_min_male: p.reference_min_male ?? null,
    reference_max_male: p.reference_max_male ?? null,
    reference_min_female: p.reference_min_female ?? null,
    reference_max_female: p.reference_max_female ?? null,
    reference_min_default: p.reference_min_default ?? null,
    reference_max_default: p.reference_max_default ?? null,
    possible_values: p.possible_values || null,
    display_order: p.display_order || 0
  });

  const handleRenameSection = async (oldName, newName) => {
    if (!newName.trim() || newName === oldName) {
      setRenamingSection(null);
      return;
    }
    const params = test.parameters.filter(p => p.section === oldName);
    setSaving(true);
    try {
      await Promise.all(params.map(p =>
        axios.put(`/api/lab/tests/${testId}/parameters/${p.id}`, buildParamPayload(p, newName.trim()))
      ));
      showFeedback('Section renamed');
      setRenamingSection(null);
      fetchTest();
    } catch (err) {
      showFeedback('Failed to rename section', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSection = (sectionName) => {
    const params = test.parameters.filter(p => p.section === sectionName);
    confirm(
      `Delete section "${sectionName}"? The ${params.length} parameter(s) inside will be moved to "Ungrouped".`,
      async () => {
        setSaving(true);
        try {
          await Promise.all(params.map(p =>
            axios.put(`/api/lab/tests/${testId}/parameters/${p.id}`, buildParamPayload(p, null))
          ));
          showFeedback('Section removed');
          fetchTest();
        } catch (err) {
          showFeedback('Failed to remove section', 'error');
        } finally {
          setSaving(false);
        }
      },
      'Delete Section'
    );
  };

  const toggleSection = (sectionName) => {
    setCollapsedSections(prev => {
      const next = new Set(prev);
      if (next.has(sectionName)) next.delete(sectionName);
      else next.add(sectionName);
      return next;
    });
  };

  const handleCreateSection = () => {
    const name = newSectionName.trim();
    if (!name) {
      setShowNewSectionInput(false);
      return;
    }
    // Check if section already exists
    if (existingSections.includes(name)) {
      showFeedback('Section already exists', 'error');
      return;
    }
    // Open add-parameter dialog pre-filled with this section
    setShowNewSectionInput(false);
    setNewSectionName('');
    openParamDialog(null, name);
  };

  // ============ Drag & drop ============

  const handleDragStart = (param) => {
    setDragItem({ paramId: param.id, fromSection: param.section || '' });
  };

  const handleDragOver = (e, param) => {
    e.preventDefault();
    setDragOverTarget({ paramId: param.id, section: param.section || '' });
  };

  const handleDragOverSection = (e, sectionName) => {
    e.preventDefault();
    setDragOverTarget({ paramId: null, section: sectionName });
  };

  const handleDrop = async (e, targetParam, targetSection) => {
    e.preventDefault();
    if (!dragItem) return;

    const allParams = [...test.parameters];
    const draggedParam = allParams.find(p => p.id === dragItem.paramId);
    if (!draggedParam) return;

    const fromSection = dragItem.fromSection;
    const toSection = targetSection;

    // Remove from current position
    const draggedIdx = allParams.indexOf(draggedParam);
    allParams.splice(draggedIdx, 1);

    // Update section if changing sections
    if (fromSection !== toSection) {
      draggedParam.section = toSection || null;
    }

    // Find target position
    let insertIdx;
    if (targetParam) {
      insertIdx = allParams.findIndex(p => p.id === targetParam.id);
      if (insertIdx === -1) insertIdx = allParams.length;
      else insertIdx += 1; // insert after target
    } else {
      // Dropped on section header — insert at beginning of section
      const firstInSection = allParams.findIndex(p => (p.section || '') === toSection);
      insertIdx = firstInSection >= 0 ? firstInSection : allParams.length;
    }

    allParams.splice(insertIdx, 0, draggedParam);

    // Optimistic update
    setTest(prev => ({ ...prev, parameters: allParams }));
    setDragItem(null);
    setDragOverTarget(null);

    // Persist reorder + section changes
    try {
      // If section changed, update the parameter's section
      if (fromSection !== toSection) {
        await axios.put(`/api/lab/tests/${testId}/parameters/${draggedParam.id}`,
          buildParamPayload(draggedParam, toSection || null)
        );
      }
      // Persist order
      await axios.put(`/api/lab/tests/${testId}/parameters/reorder`, allParams.map(p => p.id));
    } catch (err) {
      showFeedback('Failed to save changes', 'error');
      fetchTest();
    }
  };

  const handleDragEnd = () => {
    setDragItem(null);
    setDragOverTarget(null);
  };

  // ============ Sample report ============

  const handlePrintSampleReport = async (includeHeader = true) => {
    try {
      const res = await axios.get(`/api/lab/tests/${testId}/sample-report?include_header=${includeHeader}`, {
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch (err) {
      console.error('Sample report error:', err);
      // If blob response, try to read error text
      if (err.response?.data instanceof Blob) {
        const text = await err.response.data.text();
        console.error('Server error:', text);
        try {
          const json = JSON.parse(text);
          showFeedback(json.detail || 'Failed to generate sample report', 'error');
        } catch {
          showFeedback('Failed to generate sample report', 'error');
        }
      } else {
        showFeedback(err.response?.data?.detail || 'Failed to generate sample report', 'error');
      }
    }
  };

  // ============ Render ============

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!test) {
    return (
      <div className="text-center py-24">
        <p className="text-slate-500">Test not found.</p>
        <Button variant="outline" className="mt-4" onClick={() => navigate('/dashboard/lab')}>
          <ArrowLeft className="h-4 w-4 mr-2" /> Back to Lab
        </Button>
      </div>
    );
  }

  const { sections, sectionMap } = getGroupedParams();

  return (
    <div className="space-y-4 max-w-6xl mx-auto">
      {/* Feedback toast */}
      {feedback.message && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-white text-sm ${
          feedback.type === 'error' ? 'bg-red-500' : 'bg-emerald-500'
        }`}>
          {feedback.message}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard/lab')}
            className="text-slate-500 hover:text-slate-700">
            <ArrowLeft className="h-4 w-4 mr-1" /> Back
          </Button>
          <div className="h-6 w-px bg-slate-200" />
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-800">{test.name}</h1>
              <Badge variant="outline" className="text-xs font-mono">{test.test_code}</Badge>
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-500 mt-0.5">
              <span>{test.category_name}</span>
              {test.sample_type && <><span className="text-slate-300">|</span><span>{test.sample_type}</span></>}
              {test.method && <><span className="text-slate-300">|</span><span>{test.method}</span></>}
              <span className="text-slate-300">|</span>
              <span>Rs. {test.cost}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {test.parameters?.length > 0 && (
            <div className="flex gap-1">
              <Button variant="outline" size="sm" className="text-xs" onClick={() => handlePrintSampleReport(true)}>
                <Printer className="h-3.5 w-3.5 mr-1.5" /> With Header
              </Button>
              <Button variant="ghost" size="sm" className="text-xs" onClick={() => handlePrintSampleReport(false)}>
                Without Header
              </Button>
            </div>
          )}
          {showNewSectionInput ? (
            <div className="flex items-center gap-1">
              <Input
                ref={newSectionInputRef}
                value={newSectionName}
                onChange={(e) => setNewSectionName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateSection();
                  if (e.key === 'Escape') { setShowNewSectionInput(false); setNewSectionName(''); }
                }}
                onBlur={() => { if (!newSectionName.trim()) { setShowNewSectionInput(false); setNewSectionName(''); }}}
                placeholder="Section name..."
                className="h-8 w-44 text-xs"
                autoFocus
              />
              <Button size="sm" className="text-xs h-8" onClick={handleCreateSection}
                disabled={!newSectionName.trim()}>
                Create
              </Button>
              <Button size="sm" variant="ghost" className="text-xs h-8 px-2"
                onClick={() => { setShowNewSectionInput(false); setNewSectionName(''); }}>
                Cancel
              </Button>
            </div>
          ) : (
            <Button variant="outline" size="sm" className="text-xs" onClick={() => setShowNewSectionInput(true)}>
              <FolderPlus className="h-3.5 w-3.5 mr-1.5" /> Add Section
            </Button>
          )}
          <Button size="sm" className="text-xs" onClick={() => openParamDialog()}>
            <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Parameter
          </Button>
        </div>
      </div>

      {/* Parameters panel */}
      {test.parameters && test.parameters.length > 0 ? (
        <div className="space-y-3">
          {/* Stats bar */}
          <div className="flex items-center gap-4 text-xs text-slate-500 px-1">
            <span className="flex items-center gap-1">
              <Layers className="h-3.5 w-3.5" />
              {sections.filter(s => s !== '').length} section{sections.filter(s => s !== '').length !== 1 ? 's' : ''}
            </span>
            <span className="flex items-center gap-1">
              <FlaskConical className="h-3.5 w-3.5" />
              {test.parameters.length} parameter{test.parameters.length !== 1 ? 's' : ''}
            </span>
          </div>

          {/* Sections */}
          {sections.map((sectionName) => {
            const sectionParams = sectionMap[sectionName];
            const isUngrouped = sectionName === '';
            const isCollapsed = collapsedSections.has(sectionName);

            return (
              <Card key={sectionName || '__ungrouped__'} className={`overflow-hidden ${
                dragOverTarget?.section === sectionName && dragOverTarget?.paramId === null
                  ? 'ring-2 ring-indigo-300 bg-indigo-50/30'
                  : ''
              }`}>
                {/* Section header */}
                <div
                  className={`flex items-center justify-between px-4 py-2.5 cursor-pointer select-none ${
                    isUngrouped
                      ? 'bg-slate-50 border-b border-slate-100'
                      : 'bg-gradient-to-r from-indigo-50 via-slate-50 to-transparent border-b border-indigo-100'
                  }`}
                  onClick={() => toggleSection(sectionName)}
                  onDragOver={(e) => handleDragOverSection(e, sectionName)}
                  onDrop={(e) => handleDrop(e, null, sectionName)}
                >
                  <div className="flex items-center gap-2">
                    <ChevronRight className={`h-4 w-4 text-slate-400 transition-transform ${!isCollapsed ? 'rotate-90' : ''}`} />
                    {isUngrouped ? (
                      <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">General Parameters</span>
                    ) : renamingSection === sectionName ? (
                      <Input
                        ref={renameInputRef}
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onBlur={() => handleRenameSection(sectionName, renameValue)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleRenameSection(sectionName, renameValue);
                          if (e.key === 'Escape') setRenamingSection(null);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="h-6 text-xs w-48 font-semibold"
                        autoFocus
                      />
                    ) : (
                      <>
                        <FolderPlus className="h-3.5 w-3.5 text-indigo-500" />
                        <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider">{sectionName}</span>
                      </>
                    )}
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-1">{sectionParams.length}</Badge>
                  </div>
                  <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    {!isUngrouped && (
                      <>
                        <button
                          className="p-1 rounded hover:bg-white/60 text-slate-400 hover:text-slate-600 text-xs"
                          onClick={() => { setRenamingSection(sectionName); setRenameValue(sectionName); }}
                          title="Rename section"
                        >
                          <Edit2 className="h-3 w-3" />
                        </button>
                        <button
                          className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 text-xs"
                          onClick={() => handleDeleteSection(sectionName)}
                          title="Remove section"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </>
                    )}
                    <button
                      className="p-1 rounded hover:bg-indigo-100 text-indigo-500 hover:text-indigo-700 text-xs"
                      onClick={() => openParamDialog(null, sectionName)}
                      title="Add parameter to section"
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* Parameter rows */}
                {!isCollapsed && (
                  <CardContent className="p-0">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-[11px] text-slate-400 uppercase tracking-wider border-b border-slate-100 bg-white">
                            <th className="py-2 px-2 w-8"></th>
                            <th className="py-2 px-3 w-8">#</th>
                            <th className="py-2 px-3">Parameter</th>
                            <th className="py-2 px-3">Method</th>
                            <th className="py-2 px-3 w-20">Unit</th>
                            <th className="py-2 px-3 w-20">Type</th>
                            <th className="py-2 px-3">Range (M)</th>
                            <th className="py-2 px-3">Range (F)</th>
                            <th className="py-2 px-3">Range (Default)</th>
                            <th className="py-2 px-3 w-20"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {sectionParams.map((param, idx) => {
                            const globalIdx = test.parameters.indexOf(param);
                            const isDragging = dragItem?.paramId === param.id;
                            const isDragOver = dragOverTarget?.paramId === param.id && dragItem?.paramId !== param.id;

                            return (
                              <tr
                                key={param.id}
                                draggable
                                onDragStart={() => handleDragStart(param)}
                                onDragOver={(e) => handleDragOver(e, param)}
                                onDrop={(e) => handleDrop(e, param, sectionName)}
                                onDragEnd={handleDragEnd}
                                className={`border-b border-slate-50 last:border-0 transition-all group ${
                                  isDragging ? 'opacity-30 scale-[0.98]' :
                                  isDragOver ? 'bg-indigo-50 border-indigo-200 shadow-sm' :
                                  'hover:bg-slate-50/50'
                                }`}
                              >
                                <td className="py-2 px-2">
                                  <GripVertical className="h-3.5 w-3.5 text-slate-300 cursor-grab active:cursor-grabbing group-hover:text-slate-400" />
                                </td>
                                <td className="py-2 px-3 text-slate-300 text-xs font-mono">{globalIdx + 1}</td>
                                <td className="py-2 px-3">
                                  <span className="font-medium text-slate-800">{param.parameter_name}</span>
                                </td>
                                <td className="py-2 px-3 text-slate-500 text-xs">{param.method || <span className="text-slate-300">-</span>}</td>
                                <td className="py-2 px-3 text-slate-500 text-xs">{param.unit || <span className="text-slate-300">-</span>}</td>
                                <td className="py-2 px-3">
                                  <span className={`inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded ${
                                    param.field_type === 'numeric' ? 'bg-blue-50 text-blue-600' :
                                    param.field_type === 'select' ? 'bg-amber-50 text-amber-600' :
                                    'bg-slate-100 text-slate-500'
                                  }`}>{param.field_type}</span>
                                </td>
                                <td className="py-2 px-3 text-xs font-mono text-slate-500">
                                  {param.reference_min_male != null || param.reference_max_male != null
                                    ? `${param.reference_min_male ?? '–'} – ${param.reference_max_male ?? '–'}`
                                    : <span className="text-slate-300">–</span>}
                                </td>
                                <td className="py-2 px-3 text-xs font-mono text-slate-500">
                                  {param.reference_min_female != null || param.reference_max_female != null
                                    ? `${param.reference_min_female ?? '–'} – ${param.reference_max_female ?? '–'}`
                                    : <span className="text-slate-300">–</span>}
                                </td>
                                <td className="py-2 px-3 text-xs font-mono text-slate-500">
                                  {param.reference_min_default != null || param.reference_max_default != null
                                    ? `${param.reference_min_default ?? '–'} – ${param.reference_max_default ?? '–'}`
                                    : <span className="text-slate-300">–</span>}
                                </td>
                                <td className="py-2 px-3">
                                  <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-600"
                                      onClick={() => openParamDialog(param)}>
                                      <Edit2 className="h-3 w-3" />
                                    </button>
                                    <button className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500"
                                      onClick={() => handleDeleteParam(param.id)}>
                                      <Trash2 className="h-3 w-3" />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                )}
              </Card>
            );
          })}
        </div>
      ) : (
        <Card>
          <CardContent className="py-16 text-center">
            <FlaskConical className="h-12 w-12 text-slate-200 mx-auto mb-3" />
            <p className="text-sm font-medium text-slate-500">No parameters configured</p>
            <p className="text-xs text-slate-400 mt-1">Add parameters to define what values lab technicians will enter for this test.</p>
            <Button size="sm" className="mt-4 text-xs" onClick={() => openParamDialog()}>
              <Plus className="h-3.5 w-3.5 mr-1.5" /> Add First Parameter
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Add Parameter Dialog */}
      <Dialog open={showParamDialog} onOpenChange={setShowParamDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FlaskConical className="h-5 w-5 text-indigo-500" />
              {editingParam ? 'Edit Parameter' : 'Add Parameter'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
            {/* Row 1: Name + Unit + Method */}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-xs font-medium text-slate-600">Parameter Name *</Label>
                <Input value={paramForm.parameter_name}
                  onChange={(e) => setParamForm({ ...paramForm, parameter_name: e.target.value })}
                  placeholder="e.g. Hemoglobin"
                  className="mt-1" />
              </div>
              <div>
                <Label className="text-xs font-medium text-slate-600">Unit</Label>
                <Input value={paramForm.unit}
                  onChange={(e) => setParamForm({ ...paramForm, unit: e.target.value })}
                  placeholder="e.g. g/dL, mg/dL"
                  className="mt-1" />
              </div>
              <div>
                <Label className="text-xs font-medium text-slate-600">Method</Label>
                <Input value={paramForm.method}
                  onChange={(e) => setParamForm({ ...paramForm, method: e.target.value })}
                  placeholder="e.g. Colorimetric, ELISA"
                  className="mt-1" />
              </div>
            </div>

            {/* Row 2: Section + Field Type */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-medium text-slate-600">Section</Label>
                <div className="mt-1">
                  <Input
                    value={paramForm.section}
                    onChange={(e) => setParamForm({ ...paramForm, section: e.target.value })}
                    placeholder="e.g. Differential Count, Liver Enzymes"
                    list="section-suggestions"
                  />
                  {existingSections.length > 0 && (
                    <datalist id="section-suggestions">
                      {existingSections.map(s => (
                        <option key={s} value={s} />
                      ))}
                    </datalist>
                  )}
                </div>
                <p className="text-[10px] text-slate-400 mt-0.5">Group parameters under a section heading. Leave empty for ungrouped.</p>
              </div>
              <div>
                <Label className="text-xs font-medium text-slate-600">Field Type</Label>
                <Select value={paramForm.field_type}
                  onValueChange={(v) => setParamForm({ ...paramForm, field_type: v })}>
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="numeric">Numeric</SelectItem>
                    <SelectItem value="text">Text</SelectItem>
                    <SelectItem value="select">Select (Dropdown)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {paramForm.field_type === 'select' && (
              <div>
                <Label className="text-xs font-medium text-slate-600">Possible Values (comma-separated)</Label>
                <Input value={paramForm.possible_values}
                  onChange={(e) => setParamForm({ ...paramForm, possible_values: e.target.value })}
                  placeholder="e.g. Positive, Negative, Trace"
                  className="mt-1" />
              </div>
            )}

            {paramForm.field_type === 'numeric' && (
              <>
                <div className="border border-slate-200 rounded-lg p-3 space-y-3 bg-slate-50/50">
                  <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Default Reference Range</h4>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-[11px] text-slate-500">Min</Label>
                      <Input type="number" step="any" value={paramForm.reference_min_default}
                        onChange={(e) => setParamForm({ ...paramForm, reference_min_default: e.target.value })}
                        className="mt-0.5" />
                    </div>
                    <div>
                      <Label className="text-[11px] text-slate-500">Max</Label>
                      <Input type="number" step="any" value={paramForm.reference_max_default}
                        onChange={(e) => setParamForm({ ...paramForm, reference_max_default: e.target.value })}
                        className="mt-0.5" />
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <input type="checkbox" id="genderTogglePage" checked={genderSpecific}
                    onChange={(e) => setGenderSpecific(e.target.checked)}
                    className="rounded border-slate-300" />
                  <Label htmlFor="genderTogglePage" className="text-xs cursor-pointer text-slate-600">
                    Enable gender-specific reference ranges
                  </Label>
                </div>

                {genderSpecific && (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="border border-blue-100 rounded-lg p-3 space-y-2 bg-blue-50/30">
                      <h4 className="text-xs font-semibold text-blue-600 uppercase tracking-wider">Male Range</h4>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <Label className="text-[11px] text-slate-500">Min</Label>
                          <Input type="number" step="any" value={paramForm.reference_min_male}
                            onChange={(e) => setParamForm({ ...paramForm, reference_min_male: e.target.value })}
                            className="mt-0.5" />
                        </div>
                        <div>
                          <Label className="text-[11px] text-slate-500">Max</Label>
                          <Input type="number" step="any" value={paramForm.reference_max_male}
                            onChange={(e) => setParamForm({ ...paramForm, reference_max_male: e.target.value })}
                            className="mt-0.5" />
                        </div>
                      </div>
                    </div>

                    <div className="border border-pink-100 rounded-lg p-3 space-y-2 bg-pink-50/30">
                      <h4 className="text-xs font-semibold text-pink-600 uppercase tracking-wider">Female Range</h4>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <Label className="text-[11px] text-slate-500">Min</Label>
                          <Input type="number" step="any" value={paramForm.reference_min_female}
                            onChange={(e) => setParamForm({ ...paramForm, reference_min_female: e.target.value })}
                            className="mt-0.5" />
                        </div>
                        <div>
                          <Label className="text-[11px] text-slate-500">Max</Label>
                          <Input type="number" step="any" value={paramForm.reference_max_female}
                            onChange={(e) => setParamForm({ ...paramForm, reference_max_female: e.target.value })}
                            className="mt-0.5" />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <Button variant="outline" onClick={() => setShowParamDialog(false)} className="text-xs">Cancel</Button>
              <Button onClick={handleSaveParam} disabled={!paramForm.parameter_name.trim() || saving} className="text-xs">
                {saving && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
                {editingParam ? 'Update Parameter' : 'Add Parameter'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirm dialog */}
      <ConfirmDialog
        open={confirmState.open}
        title={confirmState.title}
        message={confirmState.message}
        onConfirm={() => { confirmState.onConfirm?.(); setConfirmState({ open: false }); }}
        onCancel={() => setConfirmState({ open: false })}
      />

      {saving && (
        <div className="fixed bottom-4 right-4 z-40 flex items-center gap-2 bg-slate-800 text-white text-xs px-3 py-2 rounded-lg shadow-lg">
          <Loader2 className="h-3 w-3 animate-spin" /> Saving...
        </div>
      )}
    </div>
  );
};

export default LabTestParametersPage;
