const { generate } = require('youtube-po-token-generator');

// Generate the visitorData and poToken
generate()
  .then
  (
    (result) =>
    {
      console.log("Generated Tokens:", result);
    }
  )
  .catch
  (
    (error) =>
    {
    console.error("Error generating tokens:", error);
    }
  );