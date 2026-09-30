// Dashboard: filter recommendation cards by priority.
document.querySelectorAll(".filter").forEach(function (button) {
  button.addEventListener("click", function () {
    var wanted = button.dataset.filter;
    document.querySelectorAll(".filter").forEach(function (b) {
      b.classList.toggle("active", b === button);
    });
    document.querySelectorAll(".match").forEach(function (card) {
      card.hidden = wanted !== "ALL" && card.dataset.priority !== wanted;
    });
  });
});
