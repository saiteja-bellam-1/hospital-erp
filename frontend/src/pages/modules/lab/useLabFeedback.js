import { useState } from 'react';
import { ConfirmDialog } from '../../../components/ui/confirm-dialog';

export function useLabFeedback() {
  const [feedback, setFeedback] = useState({ message: '', type: '' });
  const [confirmState, setConfirmState] = useState({ open: false });

  const showFeedback = (message, type = 'success') => {
    setFeedback({ message, type });
    setTimeout(() => setFeedback({ message: '', type: '' }), 3000);
  };

  const confirm = (message, onConfirm, title) =>
    setConfirmState({ open: true, message, onConfirm, title });

  const FeedbackToast = () => {
    if (!feedback.message) return null;
    return (
      <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-white ${
        feedback.type === 'error' ? 'bg-red-500' : 'bg-green-500'
      }`}>
        {feedback.message}
      </div>
    );
  };

  const ConfirmDialogEl = () => (
    <ConfirmDialog
      open={confirmState.open}
      title={confirmState.title}
      message={confirmState.message}
      onConfirm={() => { confirmState.onConfirm?.(); setConfirmState({ open: false }); }}
      onCancel={() => setConfirmState({ open: false })}
    />
  );

  return { showFeedback, confirm, FeedbackToast, ConfirmDialogEl };
}
