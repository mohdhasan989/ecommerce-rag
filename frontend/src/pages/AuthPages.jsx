import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { authApi, errMsg } from '../services/api';
import { Field, FormError, Spinner } from '../components/ui';
import { dateStr, isEmail } from '../utils/format';

const Shell = ({ title, sub, children }) => (
  <div className="container-x flex justify-center py-12">
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="card w-full max-w-md p-6 sm:p-8">
      <h1 className="text-2xl">{title}</h1><p className="mb-6 mt-1 text-sm text-slate-500">{sub}</p>{children}
    </motion.div>
  </div>
);

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const from = useLocation().state?.from;
  const [f, setF] = useState({ email: '', password: '' });
  const [errs, setErrs] = useState({});
  const [apiErr, setApiErr] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setApiErr('');
    const v = {};
    if (!isEmail(f.email)) v.email = 'Enter a valid email address';
    if (!f.password) v.password = 'Enter your password';
    setErrs(v); if (Object.keys(v).length) return;
    setBusy(true);
    try { const u = await login(f.email.trim(), f.password); nav(from || (u.role === 'ADMIN' ? '/admin' : '/'), { replace: true }); }
    catch (err) { setApiErr(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Shell title="Welcome back" sub="Log in to your account">
      <form onSubmit={submit} noValidate className="space-y-4">
        <FormError>{apiErr}</FormError>
        <Field label="Email" type="email" autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} error={errs.email} />
        <Field label="Password" type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} error={errs.password} />
        <button className="btn-primary w-full py-3" disabled={busy}>{busy ? <Spinner /> : 'Log in'}</button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-500">New here? <Link to="/register" className="font-medium text-brand-600 hover:underline">Create an account</Link></p>
    </Shell>
  );
}

export function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ name: '', email: '', password: '', confirm: '' });
  const [errs, setErrs] = useState({});
  const [apiErr, setApiErr] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); setApiErr('');
    const v = {};
    if (f.name.trim().length < 2) v.name = 'Enter your name';
    if (!isEmail(f.email)) v.email = 'Enter a valid email address';
    if (f.password.length < 8) v.password = 'Use at least 8 characters';
    if (f.confirm !== f.password) v.confirm = 'Passwords do not match';
    setErrs(v); if (Object.keys(v).length) return;
    setBusy(true);
    try { await register(f.name.trim(), f.email.trim(), f.password); nav('/', { replace: true }); }
    catch (err) { setApiErr(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Shell title="Create your account" sub="Start shopping in under a minute">
      <form onSubmit={submit} noValidate className="space-y-4">
        <FormError>{apiErr}</FormError>
        <Field label="Name" autoComplete="name" value={f.name} onChange={set('name')} error={errs.name} />
        <Field label="Email" type="email" autoComplete="email" value={f.email} onChange={set('email')} error={errs.email} />
        <Field label="Password" type="password" autoComplete="new-password" value={f.password} onChange={set('password')} error={errs.password} />
        <Field label="Confirm password" type="password" autoComplete="new-password" value={f.confirm} onChange={set('confirm')} error={errs.confirm} />
        <button className="btn-primary w-full py-3" disabled={busy}>{busy ? <Spinner /> : 'Register'}</button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-500">Already have an account? <Link to="/login" className="font-medium text-brand-600 hover:underline">Log in</Link></p>
    </Shell>
  );
}

export function Profile() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const [p, setP] = useState({ name: user.name, email: user.email });
  const [pe, setPe] = useState(''); const [pb, setPb] = useState(false);
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' });
  const [we, setWe] = useState(''); const [wb, setWb] = useState(false);

  const saveProfile = async (e) => {
    e.preventDefault(); setPe('');
    if (p.name.trim().length < 2) return setPe('Enter your name');
    if (!isEmail(p.email)) return setPe('Enter a valid email address');
    setPb(true);
    try { setUser(await authApi.update({ name: p.name.trim(), email: p.email.trim() })); toast('Profile updated'); } catch (err) { setPe(errMsg(err)); } finally { setPb(false); }
  };
  const savePw = async (e) => {
    e.preventDefault(); setWe('');
    if (pw.next.length < 8) return setWe('New password must be at least 8 characters');
    if (pw.next !== pw.confirm) return setWe('New passwords do not match');
    setWb(true);
    try { await authApi.changePassword({ current_password: pw.current, new_password: pw.next }); setPw({ current: '', next: '', confirm: '' }); toast('Password changed'); } catch (err) { setWe(errMsg(err)); } finally { setWb(false); }
  };
  return (
    <div className="container-x py-8">
      <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-3xl">My profile</h1><Link to="/orders" className="btn-outline">View order history</Link></div>
      <p className="mt-1 text-sm text-slate-500">Member since {dateStr(user.created_at)} · {user.role}</p>
      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <form onSubmit={saveProfile} noValidate className="card space-y-4 p-5"><h2 className="text-lg">Edit profile</h2><FormError>{pe}</FormError>
          <Field label="Name" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} />
          <Field label="Email" type="email" value={p.email} onChange={(e) => setP({ ...p, email: e.target.value })} />
          <button className="btn-primary" disabled={pb}>{pb ? <Spinner /> : 'Save changes'}</button></form>
        <form onSubmit={savePw} noValidate className="card space-y-4 p-5"><h2 className="text-lg">Change password</h2><FormError>{we}</FormError>
          <Field label="Current password" type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
          <Field label="New password" type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
          <Field label="Confirm new password" type="password" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />
          <button className="btn-primary" disabled={wb}>{wb ? <Spinner /> : 'Update password'}</button></form>
      </div>
    </div>
  );
}
