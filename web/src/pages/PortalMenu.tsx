import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Card } from "../components/ui";
import { Button } from "../components/Button";

export function PortalMenuPage() {
  const { role } = useParams<{ role: string }>();
  const portalRole = role === "admin" ? "admin" : "employee";
  const title = portalRole === "admin" ? "Admin Portal" : "Employee Portal";

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <Card className="w-full max-w-md">
        <Link to="/" className="mb-6 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Link>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        <p className="mt-2 text-sm text-slate-500">Sign in to your account or create a new one.</p>

        <div className="mt-8 space-y-3">
          <Link to={`/login/${portalRole}`} className="block">
            <Button className="w-full">Sign In</Button>
          </Link>
          <Link to={`/register/${portalRole}`} className="block">
            <Button variant="secondary" className="w-full">
              Create Account
            </Button>
          </Link>
        </div>
      </Card>
    </div>
  );
}
