import { Link } from "react-router-dom";
import { Building2, Shield, Users } from "lucide-react";
import { Card } from "../components/ui";

export function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-slate-100 to-slate-50 px-4">
      <div className="mb-10 text-center">
        <div className="mb-4 flex justify-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-700 text-white">
            <Building2 className="h-7 w-7" />
          </div>
        </div>
        <h1 className="text-3xl font-bold text-slate-900">PramaanHR</h1>
        <p className="mt-2 text-slate-500">PKI-secured Human Resource Management System</p>
      </div>

      <div className="grid w-full max-w-2xl gap-4 sm:grid-cols-2">
        <Link to="/portal/admin">
          <Card className="group cursor-pointer transition hover:border-brand-300 hover:shadow-md">
            <div className="flex items-start gap-4">
              <div className="rounded-lg bg-brand-50 p-3 text-brand-700 group-hover:bg-brand-100">
                <Shield className="h-6 w-6" />
              </div>
              <div>
                <h2 className="font-semibold text-slate-900">Admin Portal</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Manage employees, certificates, audit logs, and organizational policies.
                </p>
              </div>
            </div>
          </Card>
        </Link>

        <Link to="/portal/employee">
          <Card className="group cursor-pointer transition hover:border-brand-300 hover:shadow-md">
            <div className="flex items-start gap-4">
              <div className="rounded-lg bg-brand-50 p-3 text-brand-700 group-hover:bg-brand-100">
                <Users className="h-6 w-6" />
              </div>
              <div>
                <h2 className="font-semibold text-slate-900">Employee Portal</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Access attendance, leave, payroll, secure chat, and document signing.
                </p>
              </div>
            </div>
          </Card>
        </Link>
      </div>

      <p className="mt-8 text-xs text-slate-400">
        Certificate-based authentication · End-to-end encrypted messaging · Digital signatures
      </p>
    </div>
  );
}
