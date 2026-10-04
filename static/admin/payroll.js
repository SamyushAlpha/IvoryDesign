(function () {
  "use strict";

  function ready(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback);
    } else {
      callback();
    }
  }

  ready(function () {
    const memberField = document.getElementById("id_member");
    const salaryField = document.getElementById("id_salary_amount");
    const advancesField = document.getElementById("id_advances_to_deduct");
    if (!memberField || !salaryField) return;

    let lastAutomaticValue = "";

    function salaryEndpoint(memberId) {
      const base = window.location.pathname.replace(/(?:add|\d+\/change)\/?$/, "");
      return `${base}member-salary/${memberId}/`;
    }

    function currentRecordId() {
      const match = window.location.pathname.match(/\/(\d+)\/change\/?$/);
      return match ? match[1] : "";
    }

    function advancesEndpoint(memberId) {
      const base = window.location.pathname.replace(/(?:add|\d+\/change)\/?$/, "");
      const recordId = currentRecordId();
      return `${base}member-advances/${memberId}/${recordId ? `?record=${recordId}` : ""}`;
    }

    async function fillSalary() {
      const memberId = memberField.value;
      if (!memberId) return;

      const currentValue = salaryField.value.trim();
      if (currentValue && currentValue !== lastAutomaticValue) return;

      try {
        const response = await fetch(salaryEndpoint(memberId), {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;

        const data = await response.json();
        if (data.monthly_salary) {
          salaryField.value = data.monthly_salary;
          lastAutomaticValue = data.monthly_salary;
          salaryField.dispatchEvent(new Event("input", { bubbles: true }));
        } else if (!currentValue || currentValue === lastAutomaticValue) {
          salaryField.value = "";
          lastAutomaticValue = "";
        }
      } catch (_error) {
        // The form remains usable when the lookup is temporarily unavailable.
      }
    }

    function addAdvanceChoice(advance) {
      const label = document.createElement("label");
      label.className = "payroll-advance-choice";

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.name = "advances_to_deduct";
      checkbox.value = advance.id;
      checkbox.checked = advance.selected;

      const details = document.createElement("span");
      const amount = Number(advance.amount).toLocaleString("en-NP", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
      details.textContent = `NPR ${amount} — given ${advance.given_on}${advance.note ? ` — ${advance.note}` : ""}`;

      label.append(checkbox, details);
      advancesField.appendChild(label);
    }

    async function loadAdvances() {
      if (!advancesField) return;
      advancesField.replaceChildren();
      const memberId = memberField.value;
      if (!memberId) {
        advancesField.textContent = "Select a team member to see available advances.";
        return;
      }
      advancesField.textContent = "Loading advances…";
      try {
        const response = await fetch(advancesEndpoint(memberId), {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const data = await response.json();
        advancesField.replaceChildren();
        if (!data.advances.length) {
          advancesField.textContent = "No unused salary advances for this team member.";
          return;
        }
        data.advances.forEach(addAdvanceChoice);
      } catch (_error) {
        advancesField.textContent = "Advances could not be loaded. Refresh and try again.";
      }
    }

    memberField.addEventListener("change", fillSalary);
    memberField.addEventListener("change", loadAdvances);
    if (window.django && window.django.jQuery) {
      window.django.jQuery(memberField).on("select2:select", fillSalary);
      window.django.jQuery(memberField).on("select2:select", loadAdvances);
    }
    if (!salaryField.value.trim()) fillSalary();
    loadAdvances();
  });
})();
