import React, {
  useEffect,
  useState,
} from "react";

import AddActivityModal from "./AddActivityModal";

import { API_BASE } from "../config";

export default function ActivityPanel() {

  const [activities, setActivities] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  const [modalOpen, setModalOpen] =
    useState(false);

  // ============================================================
  // EXPORT EXCEL
  // ============================================================

  const exportExcel = () => {

    window.open(

      `${API_BASE}/api/export/activities`,

      "_blank"
    );
  };

  // ============================================================
  // FETCH ACTIVITIES
  // ============================================================

  const fetchActivities = async () => {

    try {

      const response = await fetch(
        `${API_BASE}/api/activities/`
      );

      const data = await response.json();

      setActivities(
        data.results || []
      );

    } catch (error) {

      console.error(
        "Failed to fetch activities",
        error
      );

    } finally {

      setLoading(false);
    }
  };

  // ============================================================
  // LOAD
  // ============================================================

  useEffect(() => {

    fetchActivities();

  }, []);

  // ============================================================
  // UI
  // ============================================================

  return (

    <div className="bg-white rounded-xl shadow p-6">

      {/* ====================================================== */}
      {/* HEADER */}
      {/* ====================================================== */}

      <div className="flex items-center justify-between mb-6">

        <div>

          <h2 className="text-2xl font-bold text-gray-800">
            CRM Activity Dashboard
          </h2>

          <p className="text-gray-500 text-sm">
            Calls, follow-ups, emails & remarks
          </p>

        </div>

        {/* ================================================== */}
        {/* ACTION BUTTONS */}
        {/* ================================================== */}

        <div className="flex gap-3">

          <button
            onClick={exportExcel}
            className="
              bg-green-600
              text-white
              px-4
              py-2
              rounded-lg
              hover:bg-green-700
            "
          >
            Export Excel
          </button>

          <button
            onClick={() =>
              setModalOpen(true)
            }
            className="
              bg-blue-600
              text-white
              px-4
              py-2
              rounded-lg
              hover:bg-blue-700
            "
          >
            + Add Activity
          </button>

        </div>

      </div>

      {/* ====================================================== */}
      {/* LOADING */}
      {/* ====================================================== */}

      {loading ? (

        <div className="py-10 text-center">
          Loading activities...
        </div>

      ) : (

        <div className="overflow-x-auto">

          <table className="min-w-full border">

            <thead className="bg-gray-100">

              <tr>

                <th className="p-3 text-left">
                  Company
                </th>

                <th className="p-3 text-left">
                  Contact Person
                </th>

                <th className="p-3 text-left">
                  Division
                </th>

                <th className="p-3 text-left">
                  Phone
                </th>

                <th className="p-3 text-left">
                  Activity
                </th>

                <th className="p-3 text-left">
                  Status
                </th>

                <th className="p-3 text-left">
                  Follow-up
                </th>

                <th className="p-3 text-left">
                  Remarks
                </th>

              </tr>

            </thead>

            <tbody>

              {activities.map((item) => (

                <tr
                  key={item.id}
                  className="
                    border-t
                    hover:bg-gray-50
                  "
                >

                  <td className="p-3 font-medium">
                    {item.company_name}
                  </td>

                  <td className="p-3">
                    {item.contact_person}
                  </td>

                  <td className="p-3">
                    {item.division}
                  </td>

                  <td className="p-3">
                    {item.phone}
                  </td>

                  <td className="p-3">
                    {item.activity_type}
                  </td>

                  <td className="p-3">

                    <span
                      className="
                        px-2
                        py-1
                        rounded-full
                        text-xs
                        bg-green-100
                        text-green-700
                      "
                    >
                      {item.status}
                    </span>

                  </td>

                  <td className="p-3">

                    {item.next_followup_date
                      ? new Date(
                          item.next_followup_date
                        ).toLocaleDateString()
                      : "-"}

                  </td>

                  <td className="p-3 max-w-xs">
                    {item.remarks}
                  </td>

                </tr>

              ))}

            </tbody>

          </table>

        </div>

      )}

      {/* ====================================================== */}
      {/* MODAL */}
      {/* ====================================================== */}

      <AddActivityModal

        open={modalOpen}

        onClose={() =>
          setModalOpen(false)
        }

        onSuccess={fetchActivities}
      />

    </div>
  );
}