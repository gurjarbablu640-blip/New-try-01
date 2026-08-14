import React, {
  useEffect,
  useState,
} from "react";

import { API_BASE } from "../config";

export default function TodayFollowups() {

  const [items, setItems] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  // ============================================================
  // FETCH FOLLOWUPS
  // ============================================================

  const fetchToday = async () => {

    try {

      const response = await fetch(
        `${API_BASE}/activities/today`
      );

      const data =
        await response.json();

      setItems(
        data.results || []
      );

    } catch (error) {

      console.error(error);

    } finally {

      setLoading(false);
    }
  };

  // ============================================================
  // MARK COMPLETE
  // ============================================================

  const markDone = async (id) => {

    try {

      const response = await fetch(

        `${API_BASE}/activities/complete/${id}`,

        {
          method: "PUT",
        }
      );

      const data =
        await response.json();

      if (data.success) {

        // Refresh list
        fetchToday();

      } else {

        alert(
          "Failed to update"
        );
      }

    } catch (error) {

      console.error(error);

      alert(
        "Server Error"
      );
    }
  };

  // ============================================================
  // LOAD
  // ============================================================

  useEffect(() => {

    fetchToday();

  }, []);

  // ============================================================
  // UI
  // ============================================================

  return (

    <div
      className="
        bg-white
        rounded-xl
        shadow
        p-6
      "
    >

      {/* ====================================================== */}
      {/* HEADER */}
      {/* ====================================================== */}

      <div
        className="
          flex
          items-center
          justify-between
          mb-6
        "
      >

        <div>

          <h2
            className="
              text-2xl
              font-bold
              text-gray-800
            "
          >
            Today's Followups
          </h2>

          <p
            className="
              text-sm
              text-gray-500
            "
          >
            Priority calls & pending actions
          </p>

        </div>

        <div
          className="
            bg-red-100
            text-red-700
            px-3
            py-1
            rounded-full
            text-sm
            font-medium
          "
        >
          {items.length} Pending
        </div>

      </div>

      {/* ====================================================== */}
      {/* LOADING */}
      {/* ====================================================== */}

      {loading ? (

        <div className="py-8 text-center">
          Loading followups...
        </div>

      ) : items.length === 0 ? (

        <div
          className="
            py-10
            text-center
            text-gray-500
          "
        >
          No followups today
        </div>

      ) : (

        <div className="space-y-4">

          {items.map((item) => (

            <div
              key={item.id}
              className="
                border
                rounded-lg
                p-4
                hover:bg-gray-50
              "
            >

              <div
                className="
                  flex
                  items-start
                  justify-between
                "
              >

                <div>

                  <h3
                    className="
                      text-lg
                      font-semibold
                    "
                  >
                    {item.company_name}
                  </h3>

                  <p className="text-sm text-gray-600">
                    {item.contact_person}
                  </p>

                  <p className="text-sm text-gray-600">
                    {item.phone}
                  </p>

                </div>

                <span
                  className="
                    bg-yellow-100
                    text-yellow-700
                    px-3
                    py-1
                    rounded-full
                    text-xs
                    font-medium
                  "
                >
                  {item.status}
                </span>

              </div>

              <div className="mt-3">

                <p className="text-sm text-gray-700">
                  {item.remarks}
                </p>

              </div>

              <div
                className="
                  flex
                  items-center
                  justify-between
                  mt-4
                "
              >

                <div
                  className="
                    text-sm
                    text-gray-500
                  "
                >
                  Follow-up:
                  {" "}
                  {new Date(
                    item.next_followup_date
                  ).toLocaleDateString()}
                </div>

                <button
                  onClick={() =>
                    markDone(item.id)
                  }
                  className="
                    bg-green-600
                    text-white
                    px-4
                    py-2
                    rounded-lg
                    hover:bg-green-700
                  "
                >
                  Mark Done
                </button>

              </div>

            </div>

          ))}

        </div>

      )}

    </div>
  );
}