import { AlertTriangle, Inbox, Loader2, Star } from 'lucide-react';
import { money } from '../utils/format';

export const Spinner = ({ className = '' }) => <Loader2 className={`animate-spin ${className}`} size={18} />;
export const PageSpinner = () => <div className="flex min-h-[50vh] items-center justify-center text-brand-600"><Spinner className="h-8 w-8" /></div>;
export const Skeleton = ({ className = '' }) => <div className={`animate-pulse rounded-lg bg-slate-200 ${className}`} />;

export const ErrorState = ({ message, onRetry }) => (
  <div className="card flex flex-col items-center gap-3 p-10 text-center">
    <AlertTriangle className="text-amber-500" />
    <p className="text-sm text-slate-600">{message || 'Something went wrong.'}</p>
    {onRetry && <button className="btn-outline" onClick={onRetry}>Try again</button>}
  </div>
);
export const EmptyState = ({ title, text, children }) => (
  <div className="card flex flex-col items-center gap-2 p-10 text-center">
    <Inbox className="text-slate-400" />
    <h3 className="text-base">{title}</h3>
    {text && <p className="text-sm text-slate-500">{text}</p>}
    {children && <div className="mt-2">{children}</div>}
  </div>
);

export const Field = ({ label, error, className = '', ...props }) => (
  <label className={`block ${className}`}>
    <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
    <input className={`input ${error ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : ''}`} {...props} />
    {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
  </label>
);
export const FormError = ({ children }) => children ? <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{children}</div> : null;

const STATUS = { PENDING: 'bg-amber-100 text-amber-800', PROCESSING: 'bg-blue-100 text-blue-800', SHIPPED: 'bg-indigo-100 text-indigo-800',
  DELIVERED: 'bg-emerald-100 text-emerald-800', CANCELLED: 'bg-slate-200 text-slate-700' };
export const StatusBadge = ({ status }) => <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS[status] || STATUS.PENDING}`}>{status}</span>;

export const Price = ({ p, large }) => (
  <div className="flex items-baseline gap-2">
    <span className={`${large ? 'text-2xl' : 'text-base'} font-semibold text-slate-900`}>{money(p.discount_price ?? p.price)}</span>
    {p.discount_price != null && <span className="text-sm text-slate-400 line-through">{money(p.price)}</span>}
  </div>
);
export const Rating = ({ value }) => (
  <span className="inline-flex items-center gap-1 text-sm text-slate-600"><Star size={14} className="fill-amber-400 text-amber-400" />{value.toFixed(1)}</span>
);
